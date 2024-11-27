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

class NetworkXTopo(mininet.net.Topo):
    # TODO: assert that bw, latency arguments are passed correctly
    def build(self, graph:nx.Graph, *args, **params):
        self.mn_nx_name_map = {}
        self.nx_mn_name_map = {}
        self.nx_graph = graph
        assert not graph.is_multigraph()
        self.base_nx_graph = graph.copy()

        for node in graph.nodes:
            self.addSwitch('s'+str(node), **{k: v for k, v in node.items() if k not in ['id', 'name']})
            self.mn_nx_name_map['s'+str(node)] = node
            self.nx_mn_name_map[node] = 's'+str(node)

        for end1, end2 in graph.edges:
            self.addLink('s'+str(end1), 's'+str(end2), **{k: v for k, v in graph.edges[end1, end2].items() if k not in ['source', 'target']})

        super(NetworkXTopo, self).build(**params)

    @staticmethod
    def construct_networkx_from_mininet_topo(mn_topo:mininet.net.Topo):
        nx_topo = mn_topo
        nx_topo.__class__ = NetworkXTopo # lol
        nx_topo.mn_nx_name_map = {}
        nx_topo.nx_mn_name_map = {}
        nx_topo.nx_graph = nx.Graph()

        for idx, switch in enumerate(mn_topo.switches):
            nx_topo.mn_nx_name_map[switch.name] = idx
            nx_topo.nx_mn_name_map[idx] = switch.name
            nx_topo.nx_graph.add_node(idx)

        for link in mn_topo.links:
            n1, n2 = link.intf1.node, link.intf2.node
            if (not isinstance(n1, Switch) or not isinstance(n2, Switch)):
                continue

            nx_topo.nx_graph.add_edge(nx_topo.mn_nx_name_map[n1.name], nx_topo.mn_nx_name_map[n2.name])

        nx_topo.base_nx_graph = nx_topo.nx_graph.copy()
        return nx_topo

class TopologyControlBlock():
    AVG_LINK_LATENCY_TARGET = 40
    def __init__(self, nx_topo:NetworkXTopo, event_interarrival_fn:function):
        self.nx_topo = nx_topo
        self.mininet = Mininet(self.nx_topo)
        self.event_interarrival_fn = event_interarrival_fn
        assert is_connected(self.nx_topo.nx_graph)

    async def simulate(self):
        while True:
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

