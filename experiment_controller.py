"""
Main experiment control block, passed to each process managing telemetry/traffic/topology.
Right now, it's only purpose is to generate timestamps relative to experiment's start time.
"""
import time
class ExperimentControlBlock():
    def __init__(self, config_doc:dict):
        self.start_time = time.time()


    def get_experiment_timestamp(self):
        return time.time() - self.start_time