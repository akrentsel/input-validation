"""
Main experiment starting point. 
"""
from datetime import datetime
import logging
import logging.config
from logging import FileHandler
from pathlib import Path
import yaml
from multiprocessing import Pool, Queue, Pipe
import time
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
import os

from experiment_controller import ExperimentControlBlock
from experiment_config import ExperimentConfig
from telemetry_collection.telemetry_config import ErrorGenerationConfig, TelemetryConfig
from telemetry_collection.telemetry_controller import TelemetryControlBlock
from topology.network_topo import NetworkXTopo
from topology.topology_config import NetworkEventConfig, TopologyConfig
from topology.topology_controller import TopologyControlBlock
from traffic_generation.traffic_controller import TrafficControlBlock
from traffic_generation.traffic_generation_config import TrafficGenerationConfig

logger = logging.getLogger("experiment_main")

if __name__ == "__main__":
    # mininet needs to be run in sudo.
    if os.geteuid() != 0:
        exit("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")

    config_doc = None
    with open("/home/mininet/input-validation/experiment_config.yaml") as stream:
        config_doc = yaml.safe_load(stream)

    experiment_controller = ExperimentControlBlock(config_doc)

    telemetry_config = TelemetryConfig(**config_doc['telemetry_config'])
    error_generation_config = ErrorGenerationConfig(**config_doc['error_generation_config'])
    topology_config = TopologyConfig(**config_doc['topology_config'])
    network_event_config = NetworkEventConfig(**config_doc['network_event_config'])
    traffic_generation_config = TrafficGenerationConfig(**config_doc['traffic_generation_config'])
    experiment_config = ExperimentConfig(**config_doc['experiment_config'])
    start_time = time.time()

    # for path in [Path(telemetry_config.logging_dir), Path(topology_config.logging_dir), Path(traffic_generation_config.logging_dir), Path(experiment_config.logging_dir)]:
    #     path.mkdir(exist_ok=True)

    if experiment_config.logging_config_filepath is not None:
        log_config = None
        with open(experiment_config.logging_config_filepath) as stream:
            log_config = yaml.safe_load(stream)

        logging.config.dictConfig(log_config)

    # logging.getLogger("telemetry_collection").addHandler(FileHandler(Path(telemetry_config.logging_dir) / datetime.now().strftime('telemetry_collection_log_%H_%M_%d_%m_%Y.log')))
    # logging.getLogger("topology").addHandler(FileHandler(Path(topology_config.logging_dir) / datetime.now().strftime('topology_log_%H_%M_%d_%m_%Y.log')))
    # logging.getLogger("traffic_generation").addHandler(FileHandler(Path(traffic_generation_config.logging_dir) / datetime.now().strftime('traffic_generation_log_%H_%M_%d_%m_%Y.log')))
    # logging.getLogger("experiment_main").addHandler(FileHandler(Path(experiment_config.logging_dir) / datetime.now().strftime('experiment_main_log_%H_%M_%d_%m_%Y.log')))

    controller = RemoteController('c0', ip='127.0.0.1', port=6653, protocols="OpenFlow13")
    network_topo = NetworkXTopo.construct_nx_topo_from_config(topology_config)
    mininet = Mininet(network_topo, switch=OVSSwitch, controller=controller)
    mininet.start()
    topology_controller = TopologyControlBlock(network_topo, mininet, network_event_config, topology_config)
    telemetry_controller = TelemetryControlBlock(mininet, experiment_controller, telemetry_config, error_generation_config)
    traffic_generation_controller = TrafficControlBlock(mininet, traffic_generation_config)

    logger.info("experiment starting.")
    pool = Pool(processes=3)

    proc_results = []

    def run_topology(conn):
        return topology_controller.run_simulation(conn)
    def run_telemetry(conn):
        return telemetry_controller.run_simulation(conn)
    def run_traffic(conn):
        return traffic_generation_controller.run_simulation(conn)

    with Pool(processes=3) as pool:
        early_abort = False
        
        def err_callback(err):
            logger.error("EARLY ABORT DETECTED. ABORTING.")
            pool.terminate()
            early_abort = True
            raise err
        
        (topo_snd, topo_rcv) = Pipe()
        (telemetry_snd, telemetry_rcv) = Pipe()
        (traffic_snd, traffic_rcv) = Pipe()
        proc_results.append(pool.apply_async(run_topology, [topo_rcv], error_callback=err_callback))
        proc_results.append(pool.apply_async(run_telemetry, [telemetry_rcv], error_callback=err_callback))
        proc_results.append(pool.apply_async(run_traffic, [traffic_rcv], error_callback=err_callback))


        # proc_results.append(pool.apply(run_topology, [topo_rcv]))
        # proc_results.append(pool.apply(run_telemetry, [telemetry_rcv]))
        # proc_results.append(pool.apply(run_traffic, [traffic_rcv]))

        t = 0
        while t < experiment_config.experiment_time_mins*60:
            if early_abort:
                raise RuntimeError("some processes have errored. Aborting.")
            else:
                time.sleep(5)
                t += 5

        # after the experiment duration has passed, we now signal to each of these processes to stop.
        topo_snd.send(0)
        telemetry_snd.send(0)
        traffic_snd.send(0)

        logger.info("waiting on processes.")
        for future in proc_results:
            future.get()

    logger.info("experiment finished.")