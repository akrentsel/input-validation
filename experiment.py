import time
class ExperimentControlBlock():
    def __init__(self):
        self.start_time = time.time()
    
    def get_experiment_timestamp(self):
        return time.time() - self.start_time