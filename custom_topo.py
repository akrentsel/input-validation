from mininet.node import OVSSwitch
from mininet.topo import Topo

class MyTopo( Topo ):
    "Simple topology example."

    def build( self ):
        "Create custom topo."

        # Add hosts and switches
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        s1 = self.addSwitch('s1', cls=OVSSwitch)
        s2 = self.addSwitch('s2', cls=OVSSwitch)
        
        # Add links
        self.addLink(h1, s1)
        self.addLink(s1, s2)
        self.addLink(s2, h2)
        
        # Add controller
#        self.addController('c0')

topos = { 'mytopo': ( lambda: MyTopo() ) }
