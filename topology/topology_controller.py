"""
Main controller for managing topology and random link up/down events.
We don't need to spawn a manager per process here, since there aren't 
as many events that need to be taken care of.
"""

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

        # TODO: make this frequency be a function of the number of links in the graph (duh?)
        self.event_interarrival_fn = lambda : np.random.exponential(1/network_event_config.event_interrarival_mean)
        assert is_connected(self.nx_topo.nx_graph)
        # self.kill_signal = False
        self.topology_config = topology_config

    def run_simulation(self, conn:Connection):
        """
        Main entry point for the one process managing topology changes (i.e link up/down)
        """
        try:
            logger.debug("start running topology control")
            # we listen for when main experiment spawn process (in main_experiment.py) tells
            # us to finish by listening for anything it sends along this conn object.
            while not conn.poll():
                time.sleep(self.event_interarrival_fn())

                edge = random.sample(list(set([tuple(e) for e in self.nx_topo.base_nx_graph.edges])), 1)[0]
                mn_name1, mn_name2 = self.nx_topo.nx_mn_name_map[edge[0]], self.nx_topo.nx_mn_name_map[edge[1]]
                n1, n2 = self.mininet.getNodeByName(mn_name1), self.mininet.getNodeByName(mn_name2)
                if (self.nx_topo.nx_graph.has_edge(edge[0], edge[1])):
                    self.nx_topo.nx_graph.remove_edge(edge[0], edge[1])
                    if not is_connected(self.nx_topo.nx_graph):
                        self.nx_topo.nx_graph.add_edge(edge[0], edge[1])
                        logger.debug(f"attempted to bring down link between {n1} and {n2}, but graph would be disconnected. did not do it.")
                        continue
                    else:
                        logger.debug(f"bringing down link between {n1} and {n2}")
                        self.mininet.configLinkStatus(mn_name1, mn_name2, "down")
                        for i in range(10):
                            while any([link.intf1.isUp() or link.intf2.isUp() for link in self.mininet.linksBetween(n1, n2)]):
                                self.mininet.configLinkStatus(mn_name1, mn_name2, "down")
                                time.sleep(1)

                        assert not any([link.intf1.isUp() or link.intf2.isUp() for link in self.mininet.linksBetween(n1, n2)])
                else:                    
                    logger.debug(f"bringing up link between {n1} and {n2}")
                    self.nx_topo.nx_graph.add_edge(edge[0], edge[1])
                    self.mininet.configLinkStatus(mn_name1, mn_name2, "up")

                    for i in range(10):
                        while not all([link.intf1.isUp() and link.intf2.isUp() for link in self.mininet.linksBetween(n1, n2)]):
                            self.mininet.configLinkStatus(mn_name1, mn_name2, "up")
                            time.sleep(1)

                    assert all([link.intf1.isUp() and link.intf2.isUp() for link in self.mininet.linksBetween(n1, n2)])
            logger.debug("finish running topology control.")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
