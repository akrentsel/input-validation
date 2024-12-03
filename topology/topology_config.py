from pathlib import Path
from pydantic import BaseModel
class NetworkEventConfig(BaseModel):
    event_interrarival_mean: int =  60

class TopologyConfig(BaseModel):
    # logging_dir: str
    use_bw_delay:bool = False
    
    naive_link_bw:int = 1e5
    naive_link_delay:int = 25

    use_naive_bw:bool = True
    use_naive_delay:bool = True

    topohub_name:str = None
    graph_file_path:str = None
    networkx_graph_read_function:str = None
    mininet_topo_path:str = None

    topohub_mean_link_delay:int = 25

    hosts_per_switch:int = 2