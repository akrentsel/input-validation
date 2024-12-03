'''
Manages outgoing traffic for each host.
'''
from __future__ import annotations
from typing import TYPE_CHECKING
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

from traffic_generation.iperf_stream import IperfStream, iperf_client_successful
from traffic_generation.traffic_generation_config import TrafficGenerationConfig

if TYPE_CHECKING:
    from traffic_generation.traffic_controller import TrafficControlBlock

logger = logging.getLogger("traffic_generation")
class HostTrafficManager():

    @staticmethod
    def compute_backoff_time(iperf_stream:IperfStream):
        return max(.5, min(5, 1.5**iperf_stream.retry_cnt))

    def __init__(self, host:Host, traffic_control_block:TrafficControlBlock, traffic_generation_config:TrafficGenerationConfig):
        self.flows_per_host = traffic_generation_config.flows_per_host
        self.flow_bandwidth_distribution = lambda: max(traffic_generation_config.flow_bandwidth_min, np.random.normal(traffic_generation_config.flow_bandwidth_mean, traffic_generation_config.flow_bandwidth_var))
        self.flow_duration_distribution = lambda: max(traffic_generation_config.flow_duration_min, np.random.normal(traffic_generation_config.flow_duration_mean, traffic_generation_config.flow_duration_var))
        self.error_on_stream_failure = traffic_generation_config.error_on_stream_failure
        self.traffic_control_block = traffic_control_block
        self.host:Host = host
        self.nontruant_iperf_stream_list:Collection[IperfStream] = SortedList(key=lambda stream: stream.expire_time) # maps unix timestamp to stream by expiration time
        self.truant_iperf_stream_list:Collection[IperfStream] = SortedList(key=lambda stream: stream.expire_time)
        host.cmd("iperf -s &")

    def create_stream(self, dst:Host, bw:float=10, duration:float=5.0):
        #ASSUMPTION: lock has been acquired by us (there isn't a official way of checking if we have the lock, fuck python)
        logger.debug(f"creating stream between {self.host} and {dst} with duration {duration}, bandwidth {bw}")
        iperf_popen = self.host.popen(f"iperf -c {dst.IP()} -t {duration} -b {bw}M")
        self.nontruant_iperf_stream_list.add(IperfStream(self.host, dst, iperf_popen, bw, duration))

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
        time.sleep(2*self.flow_duration_distribution())
        while not self.traffic_control_block.kill_signal: 
            while len(self.nontruant_iperf_stream_list) > 0 and self.nontruant_iperf_stream_list[0].expire_time < time.time():
                first_stream = self.nontruant_iperf_stream_list.pop()
                self.truant_iperf_stream_list.add(first_stream)

            rm_indices = []
            for idx, iperf_stream in enumerate(self.truant_iperf_stream_list):
                if iperf_stream.popen.poll() is not None:
                    (_, stderr_data) = iperf_stream.popen.communicate()
                    if not iperf_client_successful(stderr_data):
                        error_msg = f"Failed to create iperf client from host {self.host} to {iperf_stream.dst}; Logger error {stderr_data}. Is your mininet topology actually valid, and did you start your controller?"
                        if self.error_on_stream_failure:
                            raise RuntimeError(error_msg)
                        else:
                            logger.error(error_msg)
                    rm_indices.append(idx)
                else:
                    iperf_stream.retry_cnt += 1
                    if time.time() - iperf_stream.expire_time > 10:
                        logger.warning(f"stream from {iperf_stream.src} to {iperf_stream.dst} has gone severely overtime (by {time.time() - iperf_stream.expire_time} secs)")
                    
            # begin critical section; we need to check/update against total bandwidth and flow count
            self.traffic_control_block.lock.acquire()

            for idx in reversed(rm_indices):
                self.traffic_control_block.total_streams -= 1
                self.traffic_control_block.total_bw -= self.truant_iperf_stream_list[idx].bw
                del self.truant_iperf_stream_list[idx]

            streams_to_create_args = []
            for next_host in random.sample(self.traffic_control_block.host_list, self.flows_per_host - len(self.nontruant_iperf_stream_list) - len(self.truant_iperf_stream_list)):
                if next_host == self.host:
                    continue
                if (self.traffic_control_block.total_streams >= self.traffic_control_block.STREAM_LIMIT):
                    break
                bw = self.flow_bandwidth_distribution()
                if (self.traffic_control_block.total_bw + bw > self.traffic_control_block.BW_LIMIT):
                    continue
                self.traffic_control_block.total_bw += bw
                self.traffic_control_block.total_streams += 1
                duration = self.flow_duration_distribution()
                streams_to_create_args.append((self, next_host, bw, duration))

            self.traffic_control_block.lock.release()
            # end critical section

            for stream_arg in streams_to_create_args:
                HostTrafficManager.create_stream(*stream_arg)

            next_sleep_time = max(.5, min(map(lambda stream: stream.expire_time - time.time(), self.nontruant_iperf_stream_list)) if len(self.nontruant_iperf_stream_list) > 0 else 0)


            # TODO: right now exponential backoff is fucked; if we are polling for statuses of two old subprocesses w/ backoff 10s and new incoming one arrives w/ backoff .5s, we wait for the minimum time among all 3 (which is .5s).
            next_backoff_time = 10e6
            for iperf_stream in self.truant_iperf_stream_list:
                next_backoff_time = min(next_backoff_time, HostTrafficManager.compute_backoff_time(iperf_stream))

            time.sleep(min(next_sleep_time, next_backoff_time))
