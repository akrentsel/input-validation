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

from traffic_generation.host_traffic_manager import HostTrafficManager
from traffic_generation.iperf_stream import iperf_client_successful

class TrafficControlBlock():
    def __init__(self, mininet:Mininet, bw_limit:int=10e9, stream_limit:int=10e6):
        self.BW_LIMIT:int = bw_limit
        self.STREAM_LIMIT:int = stream_limit
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
            futures.append(self.thread_executor.submit(self.host_manager_map[host].run, 2*HostTrafficManager.FLOW_DURATION_DISTRIBUTION()))

        wait(futures, return_when="FIRST_EXCEPTION")
        # TODO: implement error detection on wait results
    def signal_terminate(self):
        self.kill_signal = True