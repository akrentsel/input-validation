from pathlib import Path
from pydantic import BaseModel

class ExperimentConfig(BaseModel):
    experiment_time_mins:float = 10
    logging_path: str
    