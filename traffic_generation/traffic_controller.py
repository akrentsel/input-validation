from mininet.node import Host
from mininet.net import Mininet
from collections.abc import Collection
from sortedcontainers import SortedList
import time
import random
from subprocess import Popen
from threading import Lock, Thread
from concurrent.futures import ThreadPoolExecutor, wait
import numpy as np
import logging

from traffic_generation.host_traffic_manager import HostTrafficManager
from traffic_generation.iperf_stream import iperf_client_successful
from traffic_generation.traffic_generation_config import TrafficGenerationConfig

logger = logging.getLogger("traffic_generation")
class TrafficControlBlock():
    def __init__(self, mininet:Mininet, traffic_generation_config:TrafficGenerationConfig):
        self.BW_LIMIT:int = traffic_generation_config.total_bandwidth_limit
        self.STREAM_LIMIT:int = traffic_generation_config.total_stream_limit
        self.total_bw:int = 0
        self.total_streams:int = 0
        self.host_manager_map:dict = {}
        self.host_list:Collection[Host] = list(mininet.hosts)
        self.kill_signal:bool = False # TODO: implement graceful termination...
        self.lock = Lock()
        self.thread_executor:ThreadPoolExecutor = ThreadPoolExecutor(max_workers=len(mininet.hosts))

        for host in mininet.hosts:
            self.host_manager_map[host] = HostTrafficManager(host, self)

    def run_simulation(self):
        futures = []
        for host in self.host_list:
            futures.append(self.thread_executor.submit(self.host_manager_map[host].run, 2*self.host_manager_map[host].flow_duration_distribution()))

        wait(futures, return_when="FIRST_EXCEPTION")
        # TODO: implement error detection on wait results
    def signal_terminate(self):
        self.kill_signal = True