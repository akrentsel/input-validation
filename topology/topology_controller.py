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
import random

from topology.network_topo import NetworkXTopo

class TopologyControlBlock():
    AVG_LINK_LATENCY_TARGET = 40
    def __init__(self, nx_topo:NetworkXTopo, event_interarrival_fn):
        self.nx_topo = nx_topo
        self.mininet = Mininet(self.nx_topo)
        self.event_interarrival_fn = event_interarrival_fn
        assert is_connected(self.nx_topo.nx_graph)
        self.kill_signal = False

    def simulate(self):
        while not self.kill_signal:
            asyncio.sleep(self.event_interrarival_fn())

            edge = random.sample(set([tuple(e) for e in self.nx_topo.base_nx_graph.edges]), 1)
            n1, n2 = self.mininet.getNodeByName(edge[0]), self.mininet.getNodeByName(edge[1])
            if (self.nx_topo.nx_graph.has_edge(edge[0], edge[1])):
                self.nx_topo.nx_graph.remove_edge(edge[0], edge[1])
                if not is_connected(self.nx_topo.nx_graph):
                    self.nx_topo.nx_graph.add_edge(edge[0], edge[1])
                    continue
                else:
                    self.mininet.configLinkStatus(n1, n2, "down")
                    assert not any([link.intf1.isUp() or link.intf2.isUp() for link in self.mininet.linksBetween(n1, n2)])
            else:
                self.nx_topo.nx_graph.add_edge(edge[0], edge[1])
                self.mininet.configLinkStatus(n1, n2, "up")
                assert all([link.intf1.isUp() and link.intf2.isUp() for link in self.mininet.linksBetween(n1, n2)])
    
    def kill(self):
        self.kill_signal = True

    @staticmethod
    def create_mininet_from_topohub(topo_name:str):
        topo = topohub.get("sndlib/germany50")
        g:nx.Graph = nx.node_link_graph(topo)

        
    @staticmethod
    def construct_bw_jitter_from_topohub(graph:nx.Graph):
        avg_dist = np.mean([edge['dist'] for edge in graph.edges])
        for end1, end2 in graph.edges:
            edge = graph.edges[end1, end2]
            edge['latency'] *= TopologyControlBlock.AVG_LINK_LATENCY_TARGET / avg_dist
            edge['bw'] = None
            # TODO


    @staticmethod
    def construct_mininet_from_networkx(graph:nx.Graph, enable_bw:True, enable_latency:True):
        assert not ((not enable_bw) and enable_latency)
        # TODO

