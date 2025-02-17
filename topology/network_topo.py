"""
NetworkXTopo is a class that overloads Mininet.Topo,
so that we can create mininet.Topo objects from NetworkX/TopoHub
and pass them as arguments to create mininet.Net instances based on
our topology.
"""

from pathlib import Path
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

from topology.topology_config import TopologyConfig

logger = logging.getLogger("topology")
class NetworkXTopo(Topo):
    # TODO: assert that bw, latency arguments are passed correctly
    #def __init__( self, *args, **params ):
    #    super().__init__(args, params)

    #override
    def addSwitch( self, name, **opts ):
        res = super().addSwitch(name, **opts)
        self.router_graph.add_node(name, node_type="switch")
        return res

    #override
    def addLink( self, node1, node2, port1=None, port2=None,
                 key=None, **opts): 
        if not opts and self.lopts:
            opts = self.lopts
        port1, port2 = self.addPort( node1, node2, port1, port2 )
        opts = dict( opts )
        super().addLink(node1, node2, port1, port2,
                 key, **opts)
        opts.update( node1=node1, node2=node2, port1=port1, port2=port2 )
        for k in list(opts.keys()):
            if isinstance(opts[k], dict):
                del opts[k]
                logger.warn(f"deleting entry {k} from opts")
        self.router_graph.add_edge(node1, node2, **opts)

    #override
    def addHost( self, name, **opts ):
        res = super().addHost(name, **opts)
        self.router_graph.add_node(name, node_type="host")
        return res

    def build(self, graph:nx.Graph, topology_config:TopologyConfig, **params):
        """
        this is our override, which we use to add links/switches based on 
        specified graph topology and configuration.

        ASSUMPTION: graph shows only switches/links between switches, not hosts. 
            we add hosts to each switch as specified based on the config file.
        """

        self.mn_nx_name_map = {}
        self.nx_mn_name_map = {}
        self.nx_graph = graph
        self.topology_config = topology_config

        assert not graph.is_multigraph()
        self.base_nx_graph = graph.copy()
        self.router_graph = nx.Graph()

        for node in graph.nodes:
            logger.debug(f"adding switch {'s'+str(node)}")
            s = self.addSwitch('s'+str(node), **{k: v for k, v in graph.nodes[node].items() if k not in ['id', 'name']}, protocols="OpenFlow13")
            self.mn_nx_name_map['s'+str(node)] = node
            self.nx_mn_name_map[node] = 's'+str(node)

            for i in range(self.topology_config.hosts_per_switch):
                logger.debug(f"adding host {'h'+str(i)+"_"+'s'+str(node)}")
                h = self.addHost('h'+str(i)+"_"+'s'+str(node))
                self.addLink(s, h)

        for end1, end2 in graph.edges:
            bw = None
            delay = None
            if self.topology_config.use_bw_delay:
                # try to use bw/delay parameters in each edge of graph, if they exist and config tells us to use them (i.e. if use_naive_{bw/delay} set to False); otherwise, use the naive bw/delays specified in config. 
                bw = graph.edges[end1, end2].get("bw", self.topology_config.naive_link_bw) if (not self.topology_config.use_naive_bw) else self.topology_config.naive_link_bw
                delay = graph.edges[end1, end2].get("delay", self.topology_config.naive_link_delay) if (not self.topology_config.use_naive_delay) else self.topology_config.naive_link_delay
            if (bw is None and delay is None):
                logger.debug(f"adding edge between {end1} and {end2} without bw/delay")
            else:
                logger.debug(f"adding edge between {end1} and {end2} with bw {bw}, delay {delay}")
            self.addLink('s'+str(end1), 's'+str(end2), **{k: v for k, v in graph.edges[end1, end2].items() if k not in ['source', 'target', 'bw', 'delay']}, bw=bw, delay=delay)

        super(NetworkXTopo, self).build(params)

        assert len(self.hosts()) >= 2, f"only {len(self.hosts())} found in constructed topology; expected at least 2"

    @staticmethod
    def construct_nx_topo_from_mininet_topo(mn_topo:Topo):
        """
        not currently used. TLDR: given mininet.Topo instance, create a superclass NetworkXTopo from it
        by building out a few more instance variables.
        """
        logger.info("constructing topology from mininet topology")
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

    @staticmethod
    def construct_nx_topo_from_graph_file(topology_config:TopologyConfig, **params):
        """
        called by construct_nx_topo_from_config
        """
        logger.info(f"constructing topology from graph file {topology_config.graph_file_path}")
        nx_graph = getattr(nx, topology_config.networkx_graph_read_function)(topology_config.graph_file_path)

        nx_graph = nx.relabel_nodes(nx_graph, {old_node: f"{idx}" for (idx, old_node) in enumerate(list(nx_graph.nodes(data=False)))})

        return NetworkXTopo(graph=nx_graph, topology_config=topology_config, **params)

    @staticmethod
    def construct_nx_topo_from_nx_graph(graph:nx.Graph, topology_config:TopologyConfig, **params):
        """
        called by construct_nx_topo_from_config
        """
        logger.info(f"constructing topology from networkx graph")
        return NetworkXTopo(graph=graph, topology_config=topology_config, **params)
    
    @staticmethod
    def construct_nx_topo_from_topohub(topology_config:TopologyConfig, **params):
        """
        called by construct_nx_topo_from_config
        """
        logger.info(f"constructing topology from topohub topology {topology_config.topohub_name}")
        topo = topohub.get(topology_config.topohub_name)
        nx_graph = nx.node_link_graph(topo)

        # topohub graphs tend to contain a parameter called 'distance' for every edge, which we can use
        # to construct our metric of delay; we just need to normalize to ensure that the mean delay
        # across our links is based on what is specified by topology_config.topohub_mean_link_delay.
        dist_mean = np.nanmean([nx_graph.edges[edge[0], edge[1]].get('dist', np.nan) for edge in nx_graph.edges])

        for (node1, node2) in nx_graph.edges:
            nx_graph.edges[node1, node2]['delay'] = topology_config if 'dist' not in nx_graph.edges[node1, node2] else (nx_graph.edges[node1, node2]['dist'] / dist_mean * topology_config.topohub_mean_link_delay)

        return NetworkXTopo(graph=nx_graph, topology_config=topology_config, **params)
    
    @staticmethod
    def construct_nx_topo_from_config(topology_config:TopologyConfig, **params):
        """
        main entry method for constructing mininet topology from topology config file.
        """
        if (topology_config.topohub_name is not None):
            return NetworkXTopo.construct_nx_topo_from_topohub(topology_config, **params)
        elif topology_config.graph_file_path is not None:
            assert topology_config.networkx_graph_read_function is not None, "need to specify networkX function for reading graph"

            return NetworkXTopo.construct_nx_topo_from_graph_file(topology_config, **params)
        else:
            raise ValueError("configuration file does not specify topology to import!")
