
from typing import Union
from mininet.node import Host, Switch
from mininet.net import Mininet
from collections.abc import Collection
from asyncio import get_event_loop
import json
from asyncio import Lock
from pathlib import Path
import numpy as np
import asyncio
from ovs.flow.ofp import OFPFlow
from ovs.flow.decoders import FlowEncoder
import pandas as pd
from experiment import ExperimentControlBlock
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait

class TelemetryStruct():
    def __init__(self, timestamp:float, switch_name:str):
        self.timestamp = timestamp
        self.switch_name = switch_name

    def _delay(self, new_timestamp):
        new_copy = self._copy()
        assert new_timestamp > self.timestamp
        new_copy.timestamp = new_timestamp
        return new_copy

class CounterStruct(TelemetryStruct):
    def __init__(self, timestamp:float, switch_name:str, interface_name:str, dir:str, stat_type:str, value:int):
        super(self, CounterStruct).__init__(timestamp, switch_name)
        self.interface_name = interface_name
        self.dir = dir
        self.stat_type = stat_type
        self.value = value
    
    def _copy(self):
        return CounterStruct(self.timestamp, self.switch_name, 
        self.interface_name, self.dir, self.stat_type, self.value)

    def _drop(self):
        corrupt_struct = self._copy()
        corrupt_struct.value = None
        return corrupt_struct
    
    def _multiply(self, factor):
        corrupt_struct = self._copy()
        corrupt_struct.value *= factor
        return corrupt_struct

    def _zero(self):
        corrupt_struct = self._copy()
        corrupt_struct.value = 0
        return corrupt_struct

class StatusStruct(TelemetryStruct):
    def __init__(self, timestamp:float, switch_name:str, interface_name:str, status:bool):
        super(self, StatusStruct).__init__(timestamp, switch_name)
        self.interface_name = interface_name
        self.status = status

    def _copy(self):
        return StatusStruct(self.timestamp, self.switch_name, self.interface_name, self.status)

    def _drop(self):
        corrupt_struct = self._copy()
        corrupt_struct.status = None
        return corrupt_struct
    
    def _flip(self):
        corrupt_struct = self._copy()
        corrupt_struct.status = not corrupt_struct.status
        return corrupt_struct

class FlowStruct(TelemetryStruct):
    def __init__(self, timestamp:float, switch_name:str, flow_cli_output:str):
        super(self, FlowStruct).__init__(timestamp, switch_name)
        self.match_entries = {}
        self.action_entries = {}
        self.info_entries = {}
        self.original = flow_cli_output

        ofp_parsing:dict = json.loads(json.dumps(OFPFlow(flow_cli_output).dict(), indent=4, cls=FlowEncoder))
        if "match" in ofp_parsing:
            self.match_entries = FlowStruct.flatten_dict(ofp_parsing['match'])
        if "actions" in ofp_parsing:
            self.action_entries = FlowStruct.flatten_list(ofp_parsing['actions'], 'action')
        if "info" in ofp_parsing:
            self.info_entries = FlowStruct.flatten_dict(ofp_parsing['info'])

        self.interface_name = self.info_entries['']

    def copy(self):
        return FlowStruct(self.timestamp, self.switch_name, self.original)
    def _drop(self):
        corrupt_struct = self.copy()
        for ofp_dict in [corrupt_struct.match_entries, corrupt_struct.action_entries, corrupt_struct.info_entries]:
            for k in ofp_dict.keys():
                ofp_dict[k] = None
        return corrupt_struct

    @staticmethod 
    def flatten_dict(d:dict, key_header:str="") -> dict:
        res_dict = {}
        for k, v in d.items():
            new_key = f"{key_header}_{k}" if key_header != "" else str(k) 
            if isinstance(v, list):
                for (v_k, v_v) in FlowStruct.flatten_list(v).items():
                    res_dict[f"{new_key}_{v_k}"] = v_v
            if isinstance(v, dict):
                for (v_k, v_v) in FlowStruct.flatten_dict(v).items():
                    res_dict[f"{new_key}_{v_k}"] = v_v
            else:
                res_dict[new_key] = v

        return res_dict
    
    @staticmethod
    def flatten_list(l:list, key_header:str="") -> dict:
        res_dict = {}
        for idx, v_entry in enumerate(l):
            new_key = f"{key_header}{idx}" if key_header != "" else str(idx)
            if isinstance(v_entry, dict):
                for (v_entry_k, v_entry_v) in FlowStruct.flatten_dict(v_entry).items():
                    res_dict[f"{new_key}_{v_entry_k}"] = v_entry_v
            else:
                assert not isinstance(v_entry, list)
                res_dict[new_key] = v_entry

        return res_dict

class ErrorGenerationControlBlock():
    DROP_CODE = 0
    COUNTER_SPIKE_CODE = 1
    STATUS_FLIP_CODE = 2
    COUNTER_ZERO_CODE = 3
    DELAY_CODE = 4
    def __init__(self, drop_prob:float=.01, counter_spike_prob:float=.01, status_flip_prob:float=.01, counter_zero_prob:float=.01, delay_prob:float=.01, delay_mean:float=40, delay_var:float=10, delay_min:float=20):
        self.drop_prob = drop_prob
        self.counter_spike_prob = counter_spike_prob
        self.status_flip_prob = status_flip_prob
        self.counter_zero_prob = counter_zero_prob
        self.delay_prob = delay_prob
        self.delay_time_fn = lambda : max(delay_min, np.random.normal(delay_mean, delay_var))

    def pick_error_codes(self, telemetry_type):
        picks = np.random.rand(5)
        if telemetry_type == CounterStruct:
            picks[ErrorGenerationControlBlock.STATUS_FLIP_CODE] = 1
        if telemetry_type == StatusStruct:
            picks[ErrorGenerationControlBlock.COUNTER_SPIKE_CODE, ErrorGenerationControlBlock.COUNTER_ZERO_CODE] = 1
        if telemetry_type == FlowStruct:
            picks[ErrorGenerationControlBlock.STATUS_FLIP_CODE, ErrorGenerationControlBlock.COUNTER_SPIKE_CODE, ErrorGenerationControlBlock.COUNTER_ZERO_CODE] = 1

        selected = list(np.where(picks < np.array([self.drop_prob, self.counter_spike_prob, self.status_flip_prob, self.counter_zero_prob, self.delay_prob]))[0])
        picks[picks >= np.array([self.drop_prob, self.counter_spike_prob, self.status_flip_prob, self.counter_zero_prob, self.delay_prob])] = 1
        res_codes = []

        if (ErrorGenerationControlBlock.DELAY_CODE in selected and ErrorGenerationControlBlock.DROP_CODE in selected):
            if picks[ErrorGenerationControlBlock.DELAY_CODE] < picks[ErrorGenerationControlBlock.DROP_CODE]:
                selected.remove(ErrorGenerationControlBlock.DROP_CODE)
                picks[ErrorGenerationControlBlock.DROP_CODE] = 1
            else:
                 selected.remove(ErrorGenerationControlBlock.DELAY_CODE)
                 picks[ErrorGenerationControlBlock.DELAY_CODE] = 1

        if ErrorGenerationControlBlock.DELAY_CODE in selected:
            res_codes.append(ErrorGenerationControlBlock.DELAY_CODE)
            selected.remove(ErrorGenerationControlBlock.DELAY_CODE)
            picks[ErrorGenerationControlBlock.DELAY_CODE] = 1

        if np.min(picks) == 1:
            return res_codes
        
        res_codes.append(np.argmin(picks))
        return res_codes
    
    def pick_spike_factor(self):
        return random.choice([0.1, 0.5, 2, 5, 10])
    
    def pick_delay(self):
        return self.delay_time_fn()


class TelemetryControlBlock():
    def __init__(self, mininet:Mininet, log_dir:Path, experiment_control_block:ExperimentControlBlock, collection_interval:float=10):
        self.switch_manager_map:dict = {}
        self.switch_list:Collection[Host] = list(mininet.switches)
        self.kill_signal:bool = False # TODO: implement graceful termination...
        self.lock:Lock = Lock()
        self.log_dir:Path = log_dir
        self.experiment_control_block:ExperimentControlBlock = experiment_control_block

        for switch in mininet.switches:
            self.switch_manager_map[switch.name] = SwitchTelemetryManager(switch, self, log_dir, f"baseline_telemetry_{switch.name}", f"error_telemetry_{switch.name}")

    def run_simulation(self):
        futures = []
        for host in self.switch_list:
            futures.append(self.thread_executor.submit(self.host_manager_map[host].run))

        wait(futures, return_when="FIRST_EXCEPTION")
        # TODO: implement error detection on wait results

    def signal_terminate(self):
        self.kill_signal = True

    def collate_logs(self):
        for (switch_name, switch_manager) in self.switch_manager_map.items():
            switch_manager.aggregate_logs()


class SwitchTelemetryManager():
    MAX_NUM_ROWS = 1000
    def __init__(self, switch:Switch, telemetry_control_block:TelemetryControlBlock, log_dir:Path, base_log_name_prefix:str, error_log_name_prefix:str, collection_interval:float=10, max_rows:int=MAX_NUM_ROWS, *kwargs):
        self.telemetry_control_block:TelemetryControlBlock = telemetry_control_block
        self.error_generation_control_block:ErrorGenerationControlBlock = ErrorGenerationControlBlock(self, kwargs)
        self.switch:Switch = switch
        self.base_log_struct = TelemetryLogStruct(log_dir, base_log_name_prefix, max_rows)
        self.error_log_struct = TelemetryLogStruct(log_dir, error_log_name_prefix, max_rows)
        self.collection_interval = collection_interval
        self.next_counter_collection = -1
        self.next_status_collection = -1
        self.next_flow_collection = -1

        self.delay_list = []
        self.delay_end_time = -1

    def run(self):
        timestamp = self.telemetry_control_block.experiment_control_block.get_experiment_timestamp()
        self.next_counter_collection = random.randint(timestamp, self.collection_interval)
        self.next_flow_collection = random.randint(timestamp, self.collection_interval)
        self.next_status_collection = random.randint(timestamp, self.collection_interval)

        time.sleep(max(0, self.next_counter_collection - timestamp, self.next_flow_collection - timestamp, self.next_status_collection - timestamp))

        while not self.telemetry_control_block.kill_signal:
            timestamp = self.telemetry_control_block.experiment_control_block.get_experiment_timestamp()
            if (timestamp < self.next_counter_collection):
                self.push_logs(self.collect_counters())
                self.next_counter_collection += self.collection_interval
            if (timestamp < self.next_flow_collection):
                self.push_logs(self.collect_flows())
                self.next_flow_collection += self.collection_interval
            if (timestamp < self.next_status_collection):
                self.push_logs(self.collect_statuses())
                self.next_status_collection += self.collection_interval

            time.sleep(max(0, self.next_counter_collection - timestamp, self.next_flow_collection - timestamp, self.next_status_collection - timestamp))

        # after detecting kill signal, wrap up.
        self.finalize_logs()

 
    def collect_counters(self):
        """
        Parse the output of 'ovs-ofctl dump-ports' command and extract port statistics.

        Args:
            output (str): The raw output from the 'ovs-ofctl dump-ports' command.

        Returns:
            dict: A nested dictionary with the following structure:
                {
                    'port_name': {
                        'rx': {
                            'pkts': int,
                            'bytes': int,
                            'drop': int,
                            'errs': int
                        },
                        'tx': {
                            'pkts': int,
                            'bytes': int,
                            'drop': int,
                            'errs': int
                        }
                    }
                }
            Where 'port_name' is the name or number of each port, and the nested dictionaries
            contain the receive (rx) and transmit (tx) statistics for that port.
        """
        timestamp = self.telemetry_control_block.experiment_control_block.get_experiment_timestamp()
        output = self.switch.cmd('ovs-ofctl dump-ports', self.switch.name, '-O', 'OpenFlow13')
        # Regex patterns to match lines for ports
        port_pattern = r'port\s+("?[\w-]+"?):'  # Match port names with or without quotes
        rx_pattern = r'rx pkts=(\d+), bytes=(\d+), drop=(\d+), errs=(\d+), frame=(\d+), over=(\d+), crc=(\d+)'
        tx_pattern = r'tx pkts=(\d+), bytes=(\d+), drop=(\d+), errs=(\d+), coll=(\d+)'
        
        parsed_data = []

        lines = output.splitlines()
        current_port = None

        for line in lines:
            # Match port line
            port_match = re.search(port_pattern, line)
            if port_match:
                current_port = port_match.group(1).strip('"')  # Remove quotes from port name if any
                if "-" in current_port:
                    current_port = current_port.split("-")[1]  # Remove the switch prefix if it exists
                parsed_data[current_port] = {"rx": {}, "tx": {}}

            if current_port is not None:
                # Match the RX line
                rx_match = re.search(rx_pattern, line)
                if rx_match:
                    for (stat_name, value) in [
                        ("pkts", int(rx_match.group(1))),
                        ("bytes", int(rx_match.group(2))),
                        ("drop", int(rx_match.group(3))),
                        ("errs", int(rx_match.group(4))),
                    ]:
                        parsed_data.append(CounterStruct(timestamp, self.switch.name, current_port, "rx", stat_name, value))

                # Match the TX line
                tx_match = re.search(tx_pattern, line)
                if tx_match:
                    for (stat_name, value) in [
                        ("pkts", int(tx_match.group(1))),
                        ("bytes", int(tx_match.group(2))),
                        ("drop", int(tx_match.group(3))),
                        ("errs", int(tx_match.group(4))),
                    ]:
                        parsed_data.append(CounterStruct(timestamp, self.switch.name, current_port, "tx", stat_name, value))
        return parsed_data
        
    def collect_flows(self):
        timestamp = self.telemetry_control_block.experiment_control_block.get_experiment_timestamp()
        output = self.switch.cmd('ovs-ofctl dump-flows', self.switch.name, '-O', 'OpenFlow13')

        lines = output.splitlines()
        flow_entry_list = []
        for line in lines:
            flow_entry_list.append(FlowStruct(timestamp, self.switch.name, line))

        return flow_entry_list

    def collect_statuses(self):
        status_entry_list = []
        timestamp = self.telemetry_control_block.experiment_control_block.get_experiment_timestamp()
        for iface in self.switch.intfs:
            status_entry_list.append(StatusStruct(timestamp, self.switch.name, iface.name, iface.isUp()))

        return status_entry_list


    async def push_logs(self, log_struct_list:Collection[Union[CounterStruct, StatusStruct, FlowStruct]]):
        self.base_log_struct.append_logs(log_struct_list)
        corrupt_append_list = []
        for log_struct in log_struct_list:
            error_codes = self.error_generation_control_block.pick_error_codes(type(log_struct))
        
            if (ErrorGenerationControlBlock.DROP_CODE in error_codes):
                continue
            corrupt_log_struct = log_struct
            if (ErrorGenerationControlBlock.COUNTER_SPIKE_CODE in error_codes):
                corrupt_log_struct = log_struct._multiply(ErrorGenerationControlBlock.pick_spike_factor())
            elif (ErrorGenerationControlBlock.STATUS_FLIP_CODE in error_codes):
                corrupt_log_struct = log_struct._flip()
            elif (ErrorGenerationControlBlock.COUNTER_ZERO_CODE in error_codes):
                corrupt_log_struct = log_struct._zero()
            
            delay_this = False
            if (ErrorGenerationControlBlock.DELAY_CODE in error_codes):
                new_time = corrupt_log_struct.timestamp + ErrorGenerationControlBlock.pick_delay()

                corrupt_log_struct = corrupt_log_struct._delay(new_time)

                if self.delay_end_time < 0 or (0 < self.delay_end_time <= new_time):
                    self.delay_end_time = new_time
                delay_this = True

            if (corrupt_log_struct.timestamp <= self.delay_end_time and self.delay_end_time > 0):
                corrupt_log_struct = corrupt_log_struct._delay(self.delay_end_time)
                delay_this = True

            if delay_this:
                self.delay_list.append(corrupt_log_struct)
            else:
                while (len(self.delay_list) > 0 and corrupt_log_struct.timestamp >= self.delay_list[0].timestamp):
                    corrupt_append_list.append(self.delay_list[0])
                    del self.delay_list[0]
                
                if len(self.delay_list) == 0:
                    self.delay_end_time = -1

                corrupt_append_list.append(corrupt_log_struct)
                
        self.error_log_struct.append_logs(corrupt_append_list)

    def finalize_logs(self):
        self.error_log_struct.append_logs(self.delay_list)
        self.delay_list = []
        self.delay_end_time = -1

        self.error_log_struct.write_to_disk(self.error_log_struct.get_log_path(self.error_log_struct.file_counter, False), force=True)
        self.base_log_struct.write_to_disk(self.base_log_struct.get_log_path(self.base_log_struct.file_counter, False), force=True)

        self.error_log_struct.file_counter += 1
        self.base_log_struct.file_counter += 1

    def aggregate_logs(self):
        base_df_list = []
        for i in range(self.base_log_struct.file_counter):
            base_df_list.append(pd.read_csv(self.base_log_struct.get_log_path(i, False)))

        pd.concat(base_df_list, axis=0).to_csv(self.base_log_struct.get_log_path(-1, True))
        base_df_list = []
        error_df_list = []
        for i in range(self.error_log_struct.file_counter):
            error_df_list.append(pd.read_csv(self.error_log_struct.get_log_path(i, False)))

        pd.concat(error_df_list, axis=0).to_csv(self.error_log_struct.get_log_path(-1, True))
        error_df_list = []
