'''
Manages an iperf stream between two particular hosts.
'''
from mininet.node import Host
from mininet.net import Mininet
from collections.abc import Collection
from sortedcontainers import SortedList
import time
from utils import iperf_client_successful
import random
from subprocess import Popen
from threading import Lock, Thread
from concurrent.futures import ThreadPoolExecutor, wait
import numpy as np
class IperfStream():
    def __init__(self, src:Host, dst:Host, popen:Popen, bw:int=10, duration:float=5.0,):    
        self.src: Host = src
        self.dst: Host = dst
        self.bw: int = bw
        self.popen: Popen = popen
        self.expire_time: float = time.time() + duration
        self.retry_cnt:int = 0 # we use this in HostTrafficManager.run() to implement exponential backoff for determining when to recheck statuses

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

'''
Manages outgoing traffic for each host.
'''
class HostTrafficManager():
    FLOWS_PER_HOST = 3
    FLOW_BANDWIDTH_DISTIBUTION = lambda : max(1, np.random.normal(15, 5))
    FLOW_DURATION_DISTRIBUTION = lambda : max(3, np.random.normal(10, 3))

    @staticmethod
    def compute_backoff_time(iperf_stream:IperfStream):
        return max(.5, min(5, 1.5**iperf_stream.retry_cnt))

    def __init__(self, host:Host, traffic_control_block:TrafficControlBlock):
        self.traffic_control_block = traffic_control_block
        self.host:Host = host
        self.nontruant_iperf_stream_list:Collection[IperfStream] = SortedList(key=lambda stream: stream.expire_time) # maps unix timestamp to stream by expiration time
        self.truant_iperf_stream_list:Collection[IperfStream] = SortedList(key=lambda stream: stream.expire_time)
        host.cmd("iperf -s &")

    def create_stream(self, dst:Host, bw:int=10, duration:float=5.0):
        #ASSUMPTION: lock has been acquired by us (there isn't a official way of checking if we have the lock, fuck python)

        iperf_popen = self.host.popen(f"iperf -c {dst.IP()} -t {duration} -b {bw}M")
        self.nontruant_iperf_stream_list.append(IperfStream(self.host, dst, iperf_popen, bw, duration))

    def run(self):
        # I know this "while True" structure may seem inefficient, BUT:
        # 1) in python, time.sleep() yields the thread that is running
        # 2) in python, due to GIL only one thread can run at a time even in ThreadPoolExecutors; 
        # as such, we were already fucked in terms of threading efficiency from the start lol
        # this really is I believe the best that we can do :')
        # ref: https://superfastpython.com/python-concurrency-choose-api/
        # ref: https://superfastpython.com/threadpoolexecutor-vs-threads/ 
        # PS: yes, I know about asyncio, but that doesnt seem to work here
        #     b/c cannot just use create_subprocess_shell as we need to 
        #     run them within the mininet cli, not a general shell
        while True: 
            while len(self.nontruant_iperf_stream_list) > 0 and self.nontruant_iperf_stream_list[0] < time.time():
                first_stream = self.nontruant_iperf_stream_list.pop()
                self.trunant_iperf_stream_list.append(first_stream)

            rm_indices = []
            for idx, iperf_stream in enumerate(self.truant_iperf_stream_list):
                if iperf_stream.popen.poll():
                    (_, stderr_data) = iperf_stream.popen.communicate()
                    if not iperf_client_successful(stderr_data):
                        raise RuntimeError(f"Failed to create iperf client from host {self.host} to {iperf_stream.dst}. Is your mininet topology actually valid?")
                    rm_indices.append(idx)
                else:
                    iperf_stream.retry_cnt += 1
                    
            # begin critical section; we need to check/update against total bandwidth and flow count
            self.traffic_control_block.lock.acquire()

            for idx in reversed(rm_indices):
                self.traffic_control_block.total_streams -= 1
                self.traffic_control_block.total_bw -= self.truant_iperf_stream_list[idx].bw
                del self.truant_iperf_stream_list[idx]

            streams_to_create_args = []
            for next_host in random.sample(self.traffic_control_block.host_list, len(self.nontruant_iperf_stream_list) - HostTrafficManager.FLOWS_PER_HOST):
                if next_host == self.host:
                    continue
                if (self.traffic_control_block.total_streams == self.traffic_control_block.STREAM_LIMIT):
                    break
                bw = HostTrafficManager.FLOW_BANDWIDTH_DISTIBUTION()
                if (self.traffic_control_block.total_bw + bw > self.traffic_control_block.BW_LIMIT):
                    continue
                self.traffic_control_block.total_bw += bw
                self.traffic_control_block.total_streams += 1
                duration = HostTrafficManager.FLOW_DURATION_DISTRIBUTION()
                streams_to_create_args.append((next_host, bw, duration))

            self.traffic_control_block.lock.release()
            # end critical section

            for stream_arg in streams_to_create_args:
                self.create_stream(self, *stream_arg)

            next_sleep_time = max(.5, min(map(lambda stream: stream.expire_time - time.time(), self.nontruant_iperf_stream_list)))


            # TODO: right now exponential backoff is fucked; if we are polling for statuses of two old subprocesses w/ backoff 10s and new incoming one arrives w/ backoff .5s, we wait for the minimum time among all 3 (which is .5s).
            next_backoff_time = 10e6
            for iperf_stream in self.truant_iperf_stream_list:
                next_backoff_time = min(next_backoff_time, HostTrafficManager.compute_backoff_time(iperf_stream))

            time.sleep(min(next_sleep_time, next_backoff_time))




                


