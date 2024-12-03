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
class IperfStream():
    def __init__(self, src:Host, dst:Host, popen:Popen, bw:int=10, duration:float=5.0,):    
        self.src: Host = src
        self.dst: Host = dst
        self.bw: int = bw
        self.popen: Popen = popen
        self.expire_time: float = time.time() + duration
        self.retry_cnt:int = 0 # we use this in HostTrafficManager.run() to implement exponential backoff for determining when to recheck statuses

def iperf_client_successful(msg:str) -> bool:
    return "connect failed" not in str(msg)