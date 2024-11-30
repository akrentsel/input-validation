from threading import Lock
import networkx as nx
from mininet.net import Mininet
from mininet.topo import Topo
import json
import importlib
import topohub.data
from topohub.mininet import Demands
import numpy as np
from mininet.node import Host, Switch
from networkx.algorithms.components import is_connected
import asyncio
import random
import logging

logger = logging.getLogger("topology")
class NetworkXTopo(Topo):
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
    def construct_networkx_from_mininet_topo(mn_topo:Topo):
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
