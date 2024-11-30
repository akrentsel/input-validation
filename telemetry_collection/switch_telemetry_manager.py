from __future__ import annotations
from typing import TYPE_CHECKING
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
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
import logging

from telemetry_collection.telemetry_config import TelemetryConfig
from telemetry_collection.telemetry_structs import CounterStruct, FlowStruct, StatusStruct
from telemetry_collection.telemetry_logging import TelemetryLogStruct
if TYPE_CHECKING:
    from telemetry_collection.telemetry_controller import TelemetryControlBlock, ErrorGenerationControlBlock
import logging 

logger = logging.getLogger("telemetry_collection")

class SwitchTelemetryManager():
    MAX_NUM_ROWS = 1000
    def __init__(self, switch:Switch, telemetry_control_block:TelemetryControlBlock, telemetry_config:TelemetryConfig):# switch:Switch, telemetry_control_block:TelemetryControlBlock, base_log_dir:Path, error_log_dir:Path, base_log_name_prefix:str, error_log_name_prefix:str, collection_interval:float=10, max_rows:int=MAX_NUM_ROWS, *kwargs):
        self.telemetry_control_block:TelemetryControlBlock = telemetry_control_block
        self.switch:Switch = switch
        self.base_log_struct = TelemetryLogStruct(telemetry_config.base_log_dir, f"{telemetry_config.base_log_prefix}_{switch.name}", telemetry_config.max_rows)
        self.error_log_struct = TelemetryLogStruct(telemetry_config.error_log_dir, f"{telemetry_config.error_log_prefix}_{switch.name}", telemetry_config.max_rows)
        self.collection_interval = telemetry_config.collection_interval
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
