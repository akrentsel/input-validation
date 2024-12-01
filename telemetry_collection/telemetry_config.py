from pathlib import Path
from pydantic import BaseModel
class ErrorGenerationConfig(BaseModel):
    drop_prob:float = .01
    counter_spike_prob:float = .01
    status_flip_prob:float = .01
    counter_zero_prob:float = .01
    delay_prob: float = .01
    delay_mean: float = 40.0
    delay_var:float = 10
    delay_min:float = 20

class TelemetryConfig(BaseModel):
    logging_dir: str
    base_log_dir: str
    error_log_dir: str
    collection_interval: float
    base_log_prefix: str
    error_log_prefix: str
    max_rows: int