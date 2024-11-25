import networkx as nx
import topohub.mininet
from mininet.net import Mininet


topo = topohub.mininet.TOPO_CLS['sndlib/germany50']()
mininet = Mininet(topo)

print(mininet.hosts, mininet.switches, mininet.links)
print([switch.name for switch in mininet.switches])
print([type(link) for link in mininet.links])