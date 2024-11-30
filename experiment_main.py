# from telemetry_collection.switch_telemetry_manager import *
# from telemetry_collection.telemetry_controller import *
# from telemetry_collection.telemetry_logging import *
# from telemetry_collection.telemetry_structs import *

# from topology.network_topo import *
# from topology.topology_controller import * 

# from traffic_generation.host_traffic_manager import *
# from traffic_generation.iperf_stream import *
# from traffic_generation.traffic_controller import *
import logging
from logging import FileHandler
import yaml

from experiment_config import ExperimentConfig
from telemetry_collection.telemetry_config import ErrorGenerationConfig, TelemetryConfig
from topology.topology_config import NetworkEventConfig, TopologyConfig
from traffic_generation.traffic_generation_config import TrafficGenerationConfig

logger = logging.getLogger("experiment_main")
class ExperimentControlBlock():
    def __init__(self, config_doc:dict):
        self.telemetry_config = TelemetryConfig(config_doc['telemetry_config'])
        self.error_generation_config = ErrorGenerationConfig(config_doc['error_generation_config'])
        self.topology_config = TopologyConfig(config_doc['topology_config'])
        self.network_event_config = NetworkEventConfig(config_doc['network_event_config'])
        self.traffic_generation_config = TrafficGenerationConfig(config_doc['traffic_generation_config'])
        self.experiment_config = ExperimentConfig(config_doc['experiment_config'])


        logging.getLogger("telemetry_collection").addHandler(FileHandler(self.telemetry_config.logging_path))
        logging.getLogger("topology").addHandler(FileHandler(self.topology_config.logging_path))
        logging.getLogger("traffic_generation").addHandler(FileHandler(self.traffic_generation_config.logging_path))
        logging.getLogger("experiment_main").addHandler(FileHandler(self.experiment_config.logging_path))


