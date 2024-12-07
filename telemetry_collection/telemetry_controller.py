"""
Global telemetry controller is TelemetryControlBlock here; spawns telemetry logging structs/jobs/managers for each switch.
"""
from multiprocessing.connection import Connection
from typing import Union
from mininet.node import Host, Switch
from mininet.net import Mininet
from collections.abc import Collection
from asyncio import get_event_loop
import json
from threading import Lock
from pathlib import Path
import numpy as np
import asyncio
from ovs.flow.ofp import OFPFlow
from ovs.flow.decoders import FlowEncoder
import pandas as pd
import random
import re
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
import logging

from telemetry_collection.telemetry_structs import CounterStruct, FlowStruct, StatusStruct
from telemetry_collection.switch_telemetry_manager import SwitchTelemetryManager
from experiment_controller import ExperimentControlBlock
from telemetry_collection.telemetry_config import ErrorGenerationConfig, TelemetryConfig
import logging 

logger = logging.getLogger("telemetry_collection")

"""
Used by the TelemetryControlBlock's child jobs/structs (managers/jobs for each switch)
to determine which error functions to apply.
"""
class ErrorGenerationControlBlock(object):
    DROP_CODE = 0
    COUNTER_SPIKE_CODE = 1
    STATUS_FLIP_CODE = 2
    COUNTER_ZERO_CODE = 3
    DELAY_CODE = 4
    def __init__(self, error_gen_config:ErrorGenerationConfig):
        self.config:ErrorGenerationConfig = error_gen_config

        # we pick times to delay a telemetry entry according to this distribution. 
        self.delay_time_fn = lambda : max(error_gen_config.delay_min, np.random.normal(error_gen_config.delay_mean, error_gen_config.delay_var**.5))

    def pick_error_codes(self, telemetry_type):
        """
        returns list of codes (corresponding to types of errors) to be applied.
        BUT, we need to be careful as some errors cannot be applied simultaneously.
        """
        #picks[idx] = 0 means error type with CODE=idx are more preferred to be applied.
        picks = np.random.rand(5)
        # given the telemetry type, some errors cannot be applied; we specify them here
        #   and remove them from contention
        if telemetry_type == CounterStruct:
            picks[ErrorGenerationControlBlock.STATUS_FLIP_CODE] = 1
        if telemetry_type == StatusStruct:
            picks[[ErrorGenerationControlBlock.COUNTER_SPIKE_CODE, ErrorGenerationControlBlock.COUNTER_ZERO_CODE]] = 1
        if telemetry_type == FlowStruct:
            picks[[ErrorGenerationControlBlock.STATUS_FLIP_CODE, ErrorGenerationControlBlock.COUNTER_SPIKE_CODE, ErrorGenerationControlBlock.COUNTER_ZERO_CODE]] = 1

        selected = list(np.where(picks < np.array([self.config.drop_prob, self.config.counter_spike_prob, self.config.status_flip_prob, self.config.counter_zero_prob, self.config.delay_prob]))[0])
        picks[picks >= np.array([self.config.drop_prob, self.config.counter_spike_prob, self.config.status_flip_prob, self.config.counter_zero_prob, self.config.delay_prob])] = 1

        # list of error codes to be returned, indicating errors to be applied.
        res_codes = []

        # delays and drops are incompatible, so if both selected, we remove one of them based on who "wins" 
        if (ErrorGenerationControlBlock.DELAY_CODE in selected and ErrorGenerationControlBlock.DROP_CODE in selected):
            if picks[ErrorGenerationControlBlock.DELAY_CODE] < picks[ErrorGenerationControlBlock.DROP_CODE]:
                selected.remove(ErrorGenerationControlBlock.DROP_CODE)
                picks[ErrorGenerationControlBlock.DROP_CODE] = 1
            else:
                 selected.remove(ErrorGenerationControlBlock.DELAY_CODE)
                 picks[ErrorGenerationControlBlock.DELAY_CODE] = 1

        # beyond this point, only one of delay and drop appear in `selected`
        # if delay is picked (and not dropped), this is compatible with any
        # of the remaining errors (zeros, spikes, status flips), so we 
        # guarantee it in the final results (res_codes) and update selected/picks
        # to remove it from futher consideration.
        if ErrorGenerationControlBlock.DELAY_CODE in selected:
            res_codes.append(ErrorGenerationControlBlock.DELAY_CODE)
            selected.remove(ErrorGenerationControlBlock.DELAY_CODE)
            picks[ErrorGenerationControlBlock.DELAY_CODE] = 1

        # beyond this point, either:
        # 1) delay was already picked and removed from consideration (picks[DELAY_CODE] was set to 1
        #       and drop is removed from contention (picks[DROP_CODE] = 1), 
        #     leaving only zeros, spikes, status flips in mutual contention.
        # 2) delay was not picked, meaning drops, zeros, spikes, status flips
        #      are in mutual contention. 

        # if nothing else picked, return what we have picked before.
        if np.min(picks) == 1:
            return res_codes
        
        # the remaining error types in contention in either case (1) or case (2) are mutually noncompatible,
        # so we must pick a "winner" among them
        res_codes.append(np.argmin(picks))
        return res_codes
    
    def pick_spike_factor(self):
        return random.choice([0.1, 0.5, 2, 5, 10])
    
    def pick_delay(self):
        return self.delay_time_fn()


"""
this is the "global telemetry controller" that spawns managers/jobs for each switch.
"""
class TelemetryControlBlock():
    def __init__(self, mininet:Mininet, experiment_control_block:ExperimentControlBlock, telemetry_config:TelemetryConfig, error_generation_config: ErrorGenerationConfig):
        self.switch_manager_map:dict = {}
        self.switch_list:Collection[Switch] = list(mininet.switches)
        self.kill_signal:bool = False
        self.config = telemetry_config
        self.experiment_control_block:ExperimentControlBlock = experiment_control_block
        
        #this executes jobs for telemetry logging in every switch.
        self.thread_executor:ThreadPoolExecutor = ThreadPoolExecutor(max_workers = 3 * len(self.switch_list))
        self.error_generation_control_block = ErrorGenerationControlBlock(error_generation_config)

        # telemetry logging jobs submitted to self.thread_executor write logs to disk by submitting IO jobs
        #   to this thread pool, to avoid blocking threads in self.thread_executor as much as possible.
        # (i.e. so that IO operations ideally don't block python GIL here)
        self.io_thread_executor:ThreadPoolExecutor = ThreadPoolExecutor(max_workers = 3 * len(self.switch_list))
        # every time an IO job is submitted to `self.io_thread_exectuor` from a thread in `self.thread_executor`,
        # however, it needs to log the future in this list so that the global telemetry manager thread 
        # (i.e. that running `run_simulation`) can check for potential IO job failures.
        self.io_thread_futures:Collection[Future] = []
        # to avoid races between threads when submitting/checking jobs in the above queue,
        # we make them brawl for this lock before doing so.
        self.lock = Lock()

        Path(self.config.base_log_dir).mkdir(exist_ok=False)
        if (Path(self.config.base_log_dir) != Path(self.config.error_log_dir)):
            Path(self.config.error_log_dir).mkdir(exist_ok=False)

        for switch in mininet.switches:
            # cook up a manager to manage every switch's telemetry logging.
            self.switch_manager_map[switch.name] = SwitchTelemetryManager(switch, self, self.config)

    def run_simulation(self, conn:Connection):
        try:
            logger.debug("starting telemetry simulation")
            futures = []
            for switch in self.switch_list:
                # threads here routinely manage telemetry collection for the switch they are responsible for.
                futures.append(self.thread_executor.submit(self.switch_manager_map[switch.name].run))
            
            # the conn object here is what the global experiment process (running in experiment_main.py)
            # writes to, in order to signal to us when the experiment is finished.
            while not conn.poll():
                # check for premature thread errors.
                (done_futures, notdone_futures) = wait(futures, return_when="FIRST_EXCEPTION", timeout=2)

                for future in done_futures:
                    exception = future.exception()
                    if (exception is not None):
                        raise exception

                # now, check for IO job errors (writing logs to disk).
                # this needs to be in a critical section to avoid writing to list at same time.
                self.lock.acquire()
                new_io_future_list = []
                for io_future in self.io_thread_futures:
                    if not io_future.done():
                        new_io_future_list.append(io_future)
                        continue
                    io_exception = io_future.exception()
                    if io_exception is not None:
                        raise io_exception
                self.io_thread_futures = new_io_future_list
                self.lock.release()
            
            # if we get anything from the conn object, it means the experiment has ended.
            # set this signal to true, so that any child telemetry manager will read this
            # and finish their procedure.
            if conn.poll():
                self.kill_signal = True

            # now, we wait indefinitely for all child threads to finish.
            (done_futures, notdone_futures) = wait(futures, return_when="FIRST_EXCEPTION")

            for future in done_futures:
                exception = future.exception()
                if (exception is not None):
                    raise exception
            
            # do the same with all IO jobs
            (done_io_futures, notdone_io_futures) = wait(self.io_thread_futures, return_when="FIRST_EXCEPTION")

            for io_future in done_io_futures:
                io_exception = io_future.exception()
                if (io_future.exception() is not None):
                    raise io_exception
                
            logger.debug("finished telemetry simulation; collating logs")

            # after everyone has written final logs to disk, collate each collection of logs for every switch.
            self.collate_logs()
            logger.debug("finished collating telemetry simulation logs.")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    def collate_logs(self):
        logger.debug("collating logs")
        for (switch_name, switch_manager) in self.switch_manager_map.items():
            switch_manager.aggregate_logs()
