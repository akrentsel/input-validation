from pathlib import Path
from pydantic import BaseModel
"""
Struct to hold global experiment parameters.
"""
class ExperimentConfig(BaseModel):
    experiment_time_mins:float = 10
    # logging_dir: str
    logging_config_filepath: str = None
    