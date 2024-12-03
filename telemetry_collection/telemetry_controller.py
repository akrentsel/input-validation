
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
class ErrorGenerationControlBlock(object):
    DROP_CODE = 0
    COUNTER_SPIKE_CODE = 1
    STATUS_FLIP_CODE = 2
    COUNTER_ZERO_CODE = 3
    DELAY_CODE = 4
    def __init__(self, error_gen_config:ErrorGenerationConfig):
        self.config:ErrorGenerationConfig = error_gen_config
        self.delay_time_fn = lambda : max(error_gen_config.delay_min, np.random.normal(error_gen_config.delay_mean, error_gen_config.delay_var))

    def pick_error_codes(self, telemetry_type):
        picks = np.random.rand(5)
        if telemetry_type == CounterStruct:
            picks[ErrorGenerationControlBlock.STATUS_FLIP_CODE] = 1
        if telemetry_type == StatusStruct:
            picks[[ErrorGenerationControlBlock.COUNTER_SPIKE_CODE, ErrorGenerationControlBlock.COUNTER_ZERO_CODE]] = 1
        if telemetry_type == FlowStruct:
            picks[[ErrorGenerationControlBlock.STATUS_FLIP_CODE, ErrorGenerationControlBlock.COUNTER_SPIKE_CODE, ErrorGenerationControlBlock.COUNTER_ZERO_CODE]] = 1

        selected = list(np.where(picks < np.array([self.config.drop_prob, self.config.counter_spike_prob, self.config.status_flip_prob, self.config.counter_zero_prob, self.config.delay_prob]))[0])
        picks[picks >= np.array([self.config.drop_prob, self.config.counter_spike_prob, self.config.status_flip_prob, self.config.counter_zero_prob, self.config.delay_prob])] = 1
        res_codes = []

        if (ErrorGenerationControlBlock.DELAY_CODE in selected and ErrorGenerationControlBlock.DROP_CODE in selected):
            if picks[ErrorGenerationControlBlock.DELAY_CODE] < picks[ErrorGenerationControlBlock.DROP_CODE]:
                selected.remove(ErrorGenerationControlBlock.DROP_CODE)
                picks[ErrorGenerationControlBlock.DROP_CODE] = 1
            else:
                 selected.remove(ErrorGenerationControlBlock.DELAY_CODE)
                 picks[ErrorGenerationControlBlock.DELAY_CODE] = 1

        if ErrorGenerationControlBlock.DELAY_CODE in selected:
            res_codes.append(ErrorGenerationControlBlock.DELAY_CODE)
            selected.remove(ErrorGenerationControlBlock.DELAY_CODE)
            picks[ErrorGenerationControlBlock.DELAY_CODE] = 1

        if np.min(picks) == 1:
            return res_codes
        
        res_codes.append(np.argmin(picks))
        return res_codes
    
    def pick_spike_factor(self):
        return random.choice([0.1, 0.5, 2, 5, 10])
    
    def pick_delay(self):
        return self.delay_time_fn()


class TelemetryControlBlock():
    def __init__(self, mininet:Mininet, experiment_control_block:ExperimentControlBlock, telemetry_config:TelemetryConfig, error_generation_config: ErrorGenerationConfig):
        self.switch_manager_map:dict = {}
        self.switch_list:Collection[Switch] = list(mininet.switches)
        self.kill_signal:bool = False # TODO: implement graceful termination...
        self.config = telemetry_config
        self.experiment_control_block:ExperimentControlBlock = experiment_control_block
        self.thread_executor:ThreadPoolExecutor = ThreadPoolExecutor(max_workers = 3 * len(self.switch_list))
        self.error_generation_control_block = ErrorGenerationControlBlock(error_generation_config)

        self.io_thread_executor:ThreadPoolExecutor = ThreadPoolExecutor(max_workers = 3 * len(self.switch_list))
        self.lock = Lock()
        self.io_thread_futures:Collection[Future] = []

        Path(self.config.base_log_dir).mkdir(exist_ok=False)
        if (Path(self.config.base_log_dir) != Path(self.config.error_log_dir)):
            Path(self.config.error_log_dir).mkdir(exist_ok=False)

        for switch in mininet.switches:
            self.switch_manager_map[switch.name] = SwitchTelemetryManager(switch, self, self.config)

    def run_simulation(self, conn:Connection):
        try:
            logger.debug("starting telemetry simulation")
            futures = []
            for switch in self.switch_list:
                futures.append(self.thread_executor.submit(self.switch_manager_map[switch.name].run))
            
            while not conn.poll():
                (done_futures, notdone_futures) = wait(futures, return_when="FIRST_EXCEPTION", timeout=2)

                for future in done_futures:
                    exception = future.exception()
                    if (exception is not None):
                        raise exception
                    
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
            
            if conn.poll():
                self.kill_signal = True

            (done_futures, notdone_futures) = wait(futures, return_when="FIRST_EXCEPTION")

            for future in done_futures:
                exception = future.exception()
                if (exception is not None):
                    raise exception
                
            (done_io_futures, notdone_io_futures) = wait(self.io_thread_futures, return_when="FIRST_EXCEPTION")

            for io_future in done_io_futures:
                io_exception = io_future.exception()
                if (io_future.exception() is not None):
                    raise io_exception
                
            logger.debug("finished telemetry simulation; collating logs")
            self.collate_logs()
            logger.debug("finished collating telemetry simulation logs.")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    def signal_terminate(self):
        logger.debug("kill switch flipped; terminating telemetry simulation")
        self.kill_signal = True

    def collate_logs(self):
        logger.debug("collating logs")
        for (switch_name, switch_manager) in self.switch_manager_map.items():
            switch_manager.aggregate_logs()
