"""
Global traffic controller is TrafficControlBlock here; spawns host traffic managers for each host.
"""
from pathlib import Path
from multiprocessing.connection import Connection
from mininet.node import Host
from mininet.net import Mininet
from collections.abc import Collection, Mapping
from sortedcontainers import SortedList
import time
import random
from subprocess import Popen
from threading import Lock, Thread
from concurrent.futures import ThreadPoolExecutor, wait
from experiment_controller import ExperimentControlBlock
import numpy as np
import logging
import json

from traffic_generation.host_traffic_manager import HostTrafficManager
from traffic_generation.iperf_stream import iperf_client_successful
from traffic_generation.traffic_generation_config import TrafficGenerationConfig

logger = logging.getLogger("traffic_generation")
class TrafficControlBlock():
    def __init__(self, mininet:Mininet, experiment_control_block:ExperimentControlBlock, traffic_generation_config:TrafficGenerationConfig):
        self.BW_LIMIT:int = traffic_generation_config.total_bandwidth_limit
        self.STREAM_LIMIT:int = traffic_generation_config.total_stream_limit
        self.total_bw:int = 0
        self.total_streams:int = 0
        self.host_manager_map:Mapping[Host, HostTrafficManager] = {}
        self.host_list:Collection[Host] = list(mininet.hosts)
        self.kill_signal:bool = False
        self.experiment_control_block = experiment_control_block
        self.traffic_generation_config: TrafficGenerationConfig = traffic_generation_config

        self.demand_fileno = 0
        self.host_idx_map = {host.name: idx for (idx, host) in enumerate(mininet.hosts)}
        self.idx_host_map = {idx: host.name for (idx, host) in enumerate(mininet.hosts)}
        self.timestamps = []
        self.numpy_arrs = []
        self.next_collection_schedule: float = self.experiment_control_block.get_experiment_timestamp() + random.uniform(traffic_generation_config.demand_sampling_interval, 2*traffic_generation_config.demand_sampling_interval)

        # each thread managing traffic for each host brawls for this lock
        # to up9date total_bw/stream limits.
        self.lock = Lock()
        self.thread_executor:ThreadPoolExecutor = ThreadPoolExecutor(max_workers = 3 * len(self.host_list))

        for host in mininet.hosts:
            self.host_manager_map[host] = HostTrafficManager(host, self, traffic_generation_config)

        with open(Path(self.traffic_generation_config.demand_log_dir) / "idx_host_map.json", 'w') as fp:
            json.dump(self.idx_host_map, fp)

    def get_timestamp_path(self, idx=-1):
        return Path(self.traffic_generation_config.demand_log_dir) / f"demand_timestamp_{self.demand_fileno if idx==-1 else idx}.npz"
    
    def get_arr_path(self, idx=-1):
        return Path(self.traffic_generation_config.demand_log_dir) / f"demand_array_{self.demand_fileno if idx==-1 else idx}.npz"

    def log_demand_for_host(self, demand_arr: np.array, host_manager: HostTrafficManager):
        for iperfStream in host_manager.nontruant_iperf_stream_list:
            demand_arr[self.host_idx_map[host_manager.host.name]][self.host_idx_map[iperfStream.dst.name]] = iperfStream.bw
    
    def write_to_disk(self):
        logger.debug(f"writing demands at iteration {self.demand_fileno} to disk")
        np.savez(self.get_arr_path(), np.concatenate(self.numpy_arrs))
        np.savez(self.get_timestamp_path(), np.array(self.timestamps))

        self.timestamps = []
        self.numpy_arrs = []
        self.demand_fileno += 1

    def log_demand(self):
        failed_managers:Collection[HostTrafficManager] = []
        demand_arr = np.zeros(shape=(len(self.host_list), len(self.host_list)))

        for host_manager in self.host_manager_map.values():
            if not host_manager.iperf_stream_lock.acquire(blocking=False):
                failed_managers.append(host_manager)
            else:
                self.log_demand_for_host( demand_arr, host_manager)
                host_manager.iperf_stream_lock.release()
        for host_manager in failed_managers:
            host_manager.iperf_stream_lock.acquire()
            self.log_demand_for_host( demand_arr, host_manager)
            host_manager.iperf_stream_lock.release()

        self.timestamps.append(self.experiment_control_block.get_experiment_timestamp())
        self.numpy_arrs.append(demand_arr)

        if len(self.numpy_arrs) >= self.traffic_generation_config.max_entries:
            self.write_to_disk()

    def finalize_logs(self):
        logger.debug(f"finalizing demand logs with {self.demand_fileno} logs detected")
        final_timestamp = []
        final_numpy_arrs = []
        if len(self.timestamps) > 0:
            self.write_to_disk()
        for idx in range(self.demand_fileno):
            final_timestamp.append(np.load(self.get_timestamp_path(idx)))
            final_numpy_arrs.append(np.load(self.get_arr_path(idx)))

            np.savez(Path(self.traffic_generation_config.demand_log_dir) / f"demand_timestamp_final.npz", np.concatenate(final_timestamp))
            np.savez(Path(self.traffic_generation_config.demand_log_dir) / f"demand_array_final.npz", np.concatenate(final_numpy_arrs))

    def run_simulation(self, conn:Connection):
        try:
            logger.debug(f"running traffic simulation")
            futures = []
            for host in self.host_list:
                futures.append(self.thread_executor.submit(self.host_manager_map[host].run))

            while not conn.poll():
                # routinely poll Futures to check for premature exceptions
                (done_futures, notdone_futures) = wait(futures, return_when="FIRST_EXCEPTION", timeout=max(.01, min(2, self.next_collection_schedule - self.experiment_control_block.get_experiment_timestamp())))

                for future in done_futures:
                    exception = future.exception()
                    if (exception is not None):
                        raise exception

                if (self.next_collection_schedule - self.experiment_control_block.get_experiment_timestamp() < .10):
                    if self.next_collection_schedule - self.experiment_control_block.get_experiment_timestamp() < -1.0:
                        logger.warning(f"demand collection scheduled job is tardy by at least {self.experiment_control_block.get_experiment_timestamp() - self.next_collection_schedule} seconds!")

                    logger.info("collecting traffic demand data")
                    self.log_demand()
                    self.next_collection_schedule += self.traffic_generation_config.demand_sampling_interval
            
            if conn.poll():
                self.kill_signal = True

            # now wrap things up
            (done_futures, notdone_futures) = wait(futures, return_when="FIRST_EXCEPTION")

            for future in done_futures:
                exception = future.exception()
                if (exception is not None):
                    raise exception
                
            self.finalize_logs()
            logger.debug("finished traffic simulation")
            # TODO: implement error detection on wait results
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e 