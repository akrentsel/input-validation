from pathlib import Path
from pydantic import BaseModel
class NetworkEventConfig(BaseModel):
    event_interrarival_mean: 60

class TopologyConfig(BaseModel):
    logging_path: str
    use_bw_delay:bool = False
    
    naive_link_bw:int = 1e5
    naive_link_delay:int = 25

    use_naive_bw:bool = True
    use_naive_delay:bool = True

    topohub_name:str = None
    graph_file_path:str = None
    mininet_topo_path:str = None