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

"""
Struct for spawning/managing iperf streams outgoing from the particular host
it is responsible for. Created by the global traffic controller 
(i.e. TrafficControlBlock in traffic_controller.py), one for each host.
"""
class HostTrafficManager():

    @staticmethod
    def compute_backoff_time(iperf_stream:IperfStream):
        return max(.5, min(5, 1.5**iperf_stream.retry_cnt))

    def __init__(self, host:Host, traffic_control_block:TrafficControlBlock, traffic_generation_config:TrafficGenerationConfig):
        self.flows_per_host = traffic_generation_config.flows_per_host
        self.flow_bandwidth_distribution = lambda: max(traffic_generation_config.flow_bandwidth_min, np.random.normal(traffic_generation_config.flow_bandwidth_mean, traffic_generation_config.flow_bandwidth_var**.5))
        self.flow_duration_distribution = lambda: max(traffic_generation_config.flow_duration_min, np.random.normal(traffic_generation_config.flow_duration_mean, traffic_generation_config.flow_duration_var**.5))
        self.error_on_stream_failure = traffic_generation_config.error_on_stream_failure
        self.traffic_control_block = traffic_control_block
        self.host:Host = host

        # the only two concurrent threads accessing iperf stream lists are: 1) read/writes within `run` and `create` of this class, and 2) reads only by the `run_simulation` function of TrafficController on scheduled logging of global demand data. These will only conflict if (1) is writing and (2) is reading. So we make (1) acquire this lock when writing only, and (2) acquire this lock when reading. 
        self.iperf_stream_lock: Lock = Lock()
        
        #sorted list of streams that are truant, i.e. still running beyond the timestamp we expected them to finish
        self.nontruant_iperf_stream_list:Collection[IperfStream] = SortedList(key=lambda stream: stream.expire_time)

        # sorted list of streams that are running, and are not "truant" i.e. not yet reached the timestamp they 
        # are scheduled to finish.
        self.truant_iperf_stream_list:Collection[IperfStream] = SortedList(key=lambda stream: stream.expire_time)

        # start a listening server.
        host.cmd("iperf -s &")

    def create_stream(self, dst:Host, bw:float=10, duration:float=5.0):
        #ASSUMPTION: lock has been acquired by us (there isn't a official way of checking if we have the lock, fuck python)
        logger.debug(f"creating stream between {self.host} and {dst} with duration {duration}, bandwidth {bw}")
        iperf_popen = self.host.popen(f"iperf -c {dst.IP()} -t {duration} -b {bw}M")

        # IperfStream is just a data-only struct containing those 5 variables. Importantly, it contains a Popen struct
        # that lets us check on the status of the iperf stream running in the "background".
        self.nontruant_iperf_stream_list.add(IperfStream(self.host, dst, iperf_popen, bw, duration))

    def run(self):
        time.sleep(2*self.flow_duration_distribution())
        while not self.traffic_control_block.kill_signal: 

            # begin critical section for iperf stream lock, to edit lists
            self.iperf_stream_lock.acquire()

            # first, process existing nontruant and truant stream lists.
            while len(self.nontruant_iperf_stream_list) > 0 and self.nontruant_iperf_stream_list[0].expire_time < time.time():
                first_stream = self.nontruant_iperf_stream_list.pop()
                self.truant_iperf_stream_list.add(first_stream)

            # end critical section for iperf stream lock
            self.iperf_stream_lock.release()
            
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
                    
            # begin critical section for global traffic control lock; we need to check/update against total bandwidth and flow count
            self.traffic_control_block.lock.acquire()


            # begin critical section for iperf stream lock, to edit lists
            self.iperf_stream_lock.acquire()

            # for the streams that have expired, update the total_streams and total_bw
            # so that we can eventually be allowed to create new streams to replace
            # what has ended.
            for idx in reversed(rm_indices):
                self.traffic_control_block.total_streams -= 1
                self.traffic_control_block.total_bw -= self.truant_iperf_stream_list[idx].bw
                del self.truant_iperf_stream_list[idx]

            # end critical section for iperf stream lock
            self.iperf_stream_lock.release()

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

            # end critical section for global traffic control lock
            self.traffic_control_block.lock.release()

            # begin critical section for iperf stream lock, to edit lists
            self.iperf_stream_lock.acquire()

            for stream_arg in streams_to_create_args:
                HostTrafficManager.create_stream(*stream_arg)

            # end critical section for iperf stream lock
            self.iperf_stream_lock.release()

            # we compute how long we sleep based on:
            #  1) until when the next nontruant iperf stream expires.
            #  2) until when we want to next check on the truant iperf streams.


            # part (1) of sleep time computation
            next_sleep_time = max(.5, min(map(lambda stream: stream.expire_time - time.time(), self.nontruant_iperf_stream_list)) if len(self.nontruant_iperf_stream_list) > 0 else 0)

            # part (2) of sleep time computation.
            # TODO: right now exponential backoff is fucked; if we are polling for statuses of two old subprocesses w/ backoff 10s and new incoming one arrives w/ backoff .5s, we wait for the minimum time among all 3 (which is .5s).
            next_backoff_time = 10e6
            for iperf_stream in self.truant_iperf_stream_list:
                next_backoff_time = min(next_backoff_time, HostTrafficManager.compute_backoff_time(iperf_stream))

            # and finally, take a break :)
            time.sleep(min(next_sleep_time, next_backoff_time))
