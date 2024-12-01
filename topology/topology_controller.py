from datetime import datetime
from multiprocessing import Pipe
import multiprocessing
from multiprocessing.connection import Connection
from pathlib import Path
from threading import Lock
import networkx as nx
import mininet
from mininet.net import Mininet
import json
import importlib
import topohub.data
from topohub.mininet import Demands
import numpy as np
from mininet.node import Host, Switch
from networkx.algorithms.components import is_connected
import asyncio
import time
import random
import logging
import sys
from topology.topology_config import NetworkEventConfig, TopologyConfig
from topology.network_topo import NetworkXTopo

logger = logging.getLogger("topology")
class TopologyControlBlock():
    AVG_LINK_LATENCY_TARGET = 40
    def __init__(self, nx_topo:NetworkXTopo, mininet:Mininet, network_event_config:NetworkEventConfig, topology_config: TopologyConfig):
        self.nx_topo = nx_topo
        self.mininet = mininet
        self.event_interarrival_fn = lambda : np.random.exponential(network_event_config.event_interrarival_mean)
        assert is_connected(self.nx_topo.nx_graph)
        # self.kill_signal = False
        self.topology_config = topology_config


    # def __getstate__(self):
    #     state = self.__dict__.copy()
    #     # Don't pickle baz
    #     del state["mininet"]
    #     del state["event_interrarival_fn"]
    #     return state

    # def __setstate__(self, state):
    #     self.__dict__.update(state)
    #     # Add baz back since it doesn't exist in the pickle
    #     self.mininet = None
    #     self.event_interarrival_fn = None

    def run_simulation(self, conn:Connection):
        try:
            logger.debug("start running topology control")
            while not conn.poll():
                time.sleep(self.event_interarrival_fn())

                edge = random.sample(set([tuple(e) for e in self.nx_topo.base_nx_graph.edges]), 1)
                n1, n2 = self.mininet.getNodeByName(edge[0]), self.mininet.getNodeByName(edge[1])
                if (self.nx_topo.nx_graph.has_edge(edge[0], edge[1])):
                    self.nx_topo.nx_graph.remove_edge(edge[0], edge[1])
                    if not is_connected(self.nx_topo.nx_graph):
                        self.nx_topo.nx_graph.add_edge(edge[0], edge[1])
                        continue
                    else:
                        logger.debug(f"bringing down link between {n1} and {n2}")
                        self.mininet.configLinkStatus(n1, n2, "down")
                        assert not any([link.intf1.isUp() or link.intf2.isUp() for link in self.mininet.linksBetween(n1, n2)])
                else:                    
                    logger.debug(f"bringing up link between {n1} and {n2}")
                    self.nx_topo.nx_graph.add_edge(edge[0], edge[1])
                    self.mininet.configLinkStatus(n1, n2, "up")
                    assert all([link.intf1.isUp() and link.intf2.isUp() for link in self.mininet.linksBetween(n1, n2)])
            logger.debug("finish running topology control.")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    def kill(self):                    
        logger.debug(f"kill switch flipped; terminating topology simulation")
        self.kill_signal = True
