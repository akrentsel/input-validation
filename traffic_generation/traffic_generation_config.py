from pathlib import Path
from pydantic import BaseModel
import numpy as np

class TrafficGenerationConfig(BaseModel):
    logging_path: str
    flow_bandwidth_min: float = 1
    flow_bandwidth_mean: float = 15
    flow_bandwidth_var: float = 5

    flow_duration_min: float = 3
    flow_duration_mean: float = 10
    flow_duration_var: float = 3

    flows_per_host: int = 3

    total_bandwidth_limit:float = 3.0e4
    total_stream_limit:int = 10e3

