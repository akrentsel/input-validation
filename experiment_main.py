# from telemetry_collection.switch_telemetry_manager import *
# from telemetry_collection.telemetry_controller import *
# from telemetry_collection.telemetry_logging import *
# from telemetry_collection.telemetry_structs import *

# from topology.network_topo import *
# from topology.topology_controller import * 

# from traffic_generation.host_traffic_manager import *
# from traffic_generation.iperf_stream import *
# from traffic_generation.traffic_controller import *
import datetime
import logging
from logging import FileHandler
from pathlib import Path
import yaml
from multiprocessing import Pool
import time
from mininet.net import Mininet

from experiment_config import ExperimentConfig
from telemetry_collection.telemetry_config import ErrorGenerationConfig, TelemetryConfig
from telemetry_collection.telemetry_controller import TelemetryControlBlock
from topology.network_topo import NetworkXTopo
from topology.topology_config import NetworkEventConfig, TopologyConfig
from topology.topology_controller import TopologyControlBlock
from traffic_generation.traffic_controller import TrafficControlBlock
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
        self.start_time = time.time()

        for path in [Path(self.telemetry_config.logging_dir), Path(self.topology_config.logging_dir), Path(self.traffic_generation_config.logging_dir), Path(self.experiment_config.logging_dir)]:
            path.mkdir(exist_ok=True)

        logging.getLogger("telemetry_collection").addHandler(FileHandler(Path(self.telemetry_config.logging_dir) / datetime.now().strftime('telemetry_collection_log_%H_%M_%d_%m_%Y.log')))
        logging.getLogger("topology").addHandler(FileHandler(Path(self.topology_config.logging_dir) / datetime.now().strftime('topology_log_%H_%M_%d_%m_%Y.log')))
        logging.getLogger("traffic_generation").addHandler(FileHandler(Path(self.traffic_generation_config.logging_dir) / datetime.now().strftime('traffic_generation_log_%H_%M_%d_%m_%Y.log')))
        logging.getLogger("experiment_main").addHandler(FileHandler(Path(self.experiment_config.logging_dir) / datetime.now().strftime('experiment_main_log_%H_%M_%d_%m_%Y.log')))

        self.network_topo = NetworkXTopo.construct_nx_topo_from_config(self.topology_config)
        self.mininet = Mininet(self.nx_topo)
        self.topology_controller = TopologyControlBlock(self.network_topo, self.network_event_config)
        self.telemetry_controller = TelemetryControlBlock(self.mininet, self, self.telemetry_config)
        self.traffic_generation_controller = TrafficControlBlock(self.mininet, self.traffic_generation_config)

    def get_experiment_timestamp(self):
        return time.time() - self.start_time
    
    def run(self):
        logger.info("experiment starting.")
        pool = Pool(processes=3)

        def err_callback(err):
            raise err
        proc_results = []
        with Pool(processes=3) as pool:
            proc_results.append(pool.apply_async(self.topology_controller.run_simulation, [self.topology_controller], error_callback=err_callback))
            proc_results.append(pool.apply_async(self.telemetry_controller.run_simulation, [self.telemetry_controller], error_callback=err_callback))
            proc_results.append(pool.apply_async(self.traffic_generation_controller.run_simulation, [self.traffic_generation_controller], error_callback=err_callback))

        time.sleep(self.experiment_config.experiment_time_mins)

        for future in proc_results:
            future.get()

        logger.info("experiment finished.")


if __name__ == "__main__":
    config = yaml.load("/home/mininet/input-validation/experiment_config.yaml")

    experiment_controller = ExperimentControlBlock(config)
    experiment_controller.run()