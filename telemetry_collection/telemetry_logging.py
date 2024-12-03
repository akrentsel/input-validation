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
from experiment_controller import ExperimentControlBlock
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
from telemetry_collection.telemetry_structs import FlowStruct, CounterStruct, StatusStruct
from experiment_controller import ExperimentControlBlock
import logging 

if TYPE_CHECKING:
    from telemetry_collection.switch_telemetry_manager import SwitchTelemetryManager

logger = logging.getLogger("telemetry_collection")
class TelemetryLogStruct():
    MIN_WRITE_LEN = 500
    def __init__(self, switch_telemetry_controller:SwitchTelemetryManager, log_dir:str, log_prefix:str, max_rows):
        self.num_entries = 0
        self.log_dir = Path(log_dir)
        self.log_prefix = log_prefix
        self.file_counter = 0
        self.max_rows = max_rows
        self.switch_telemetry_manager = switch_telemetry_controller

        # common
        self.timestamp_list = []
        # self.hosts = []
        self.router_name_list = []
        self.telemetry_type_list = []
        self.error_gen_list = []

        # interface counter telemetry
        self.interface_name_list = []
        self.direction_list = []
        self.counter_type_list = []
        self.counter_val_list = []

        # flow table telemetry
        self.match_dict_list = {}
        self.action_dict_list = {}
        self.info_dict_list = {}

    # @staticmethod
    # def corrupt_multiply(counter_struct:CounterStruct, factor:float):
    #     return CounterStruct(counter_struct.timestamp, counter_struct.switch_name, counter_struct.interface_name, counter_struct.dir, counter_struct.stat_type, counter_struct.value*factor)
    
    # @staticmethod
    # def corrupt_drop(telemetry_struct:TelemetryStruct):
    #     return telemetry_struct._drop()

    def _append_counter(self, counter_struct:CounterStruct):
        self.timestamp_list.append(counter_struct.timestamp)
        self.router_name_list.append(counter_struct.switch_name)
        self.error_gen_list.append(" - ".join(counter_struct.errors_applied))
        self.telemetry_type_list.append("counter")

        self.interface_name_list.append(counter_struct.interface_name)
        self.direction_list.append(counter_struct.dir)
        self.counter_type_list.append(counter_struct.stat_type)
        self.counter_val_list.append(counter_struct.value)

        for _, v in self.match_dict_list.items():
            v.append(None)

        for _, v in self.action_dict_list.items():
            v.append(None)

        for _, v in self.info_dict_list.items():
            v.append(None)

        self.num_entries += 1
    def _append_status(self, status_struct:StatusStruct):
        self.timestamp_list.append(status_struct.timestamp)
        self.router_name_list.append(status_struct.switch_name)
        self.error_gen_list.append(" - ".join(status_struct.errors_applied))
        self.telemetry_type_list.append("status")

        self.interface_name_list.append(status_struct.interface_name)
        self.direction_list.append(None)
        self.counter_type_list.append("iface_status")
        self.counter_val_list.append(status_struct.status)

        for _, v in self.match_dict_list.items():
            v.append(None)

        for _, v in self.action_dict_list.items():
            v.append(None)

        for _, v in self.info_dict_list.items():
            v.append(None)

        self.num_entries += 1
    
    def _append_flow(self, flow_struct:FlowStruct):
        self.num_entries += 1
        self.timestamp_list.append(flow_struct.timestamp)
        self.router_name_list.append(flow_struct.switch_name)
        self.error_gen_list.append(" - ".join(flow_struct.errors_applied))
        self.telemetry_type_list.append("flow_entry")

        self.interface_name_list.append(None)
        self.direction_list.append(None)
        self.counter_type_list.append(None)
        self.counter_val_list.append(None)


        for log_dict, flow_dict in [(self.match_dict_list, flow_struct.match_entries), (self.action_dict_list, flow_struct.action_entries), (self.info_dict_list, flow_struct.info_entries)]:
            for k, lst in log_dict.items():
                if k in flow_dict:
                    lst.append(flow_dict[k])
                else:
                    lst.append(None)

            for k, lst in flow_dict.items():
                if k not in log_dict:
                    log_dict[k] = [None for _ in range(self.num_entries)]


    def get_idx_before(self, timestamp:int):
        for i in range(len(self.timestamp_list)):
            if self.timestamp_list[i] > timestamp:
                return i - 1
        return -1
    
    def get_log_path(self, file_idx:int, aggregated:bool=False):
        return self.log_dir / f"{self.log_prefix}_{file_idx}.csv" if not aggregated else self.log_dir / f"{self.log_prefix}_aggregated.csv"

    def write_to_disk(self, path:Path, idx_before:int=-1, force=True)->bool:
        # idx_before = self.get_idx_before(timestamp_before)
        if idx_before == -1:
            idx_before = len(self.timestamp_list)
        if (idx_before < TelemetryLogStruct.MIN_WRITE_LEN - 1 and not force):
            return False
        
        logger.debug(f"submitting disk write request for: {path}")

        df_dict = {"timestamp": self.timestamp_list[:idx_before], "errors_applied": self.error_gen_list[:idx_before], "router_name": self.router_name_list[:idx_before], "telemetry_type":self.telemetry_type_list[:idx_before], "interface_name": self.interface_name_list[:idx_before], "counter_direction": self.direction_list[:idx_before], "counter_type": self.counter_type_list[:idx_before], "counter_val": self.counter_val_list[:idx_before]}
        for dict_list in [self.info_dict_list, self.match_dict_list, self.action_dict_list]:
            for k, v in dict_list.items():
                df_dict[k] = v[:idx_before]

        self.switch_telemetry_manager.telemetry_control_block.lock.acquire()
        self.switch_telemetry_manager.telemetry_control_block.io_thread_futures.append(self.switch_telemetry_manager.telemetry_control_block.io_thread_executor.submit(TelemetryLogStruct.write_to_disk_async, path, df_dict))
        self.switch_telemetry_manager.telemetry_control_block.lock.release()

        self.timestamp_list = self.timestamp_list[idx_before:]
        self.error_gen_list = self.error_gen_list[idx_before:]
        self.router_name_list = self.router_name_list[idx_before:]
        self.telemetry_type_list = self.telemetry_type_list[idx_before:]
        self.interface_name_list = self.interface_name_list[idx_before:]
        self.direction_list = self.direction_list[idx_before:]
        self.counter_type_list = self.counter_type_list[idx_before:]
        self.counter_val_list = self.counter_val_list[idx_before:]

        for dict_list in [self.info_dict_list, self.match_dict_list, self.action_dict_list]:
            for k, v in dict_list.items():
                dict_list[k] = v[idx_before:]

        return True

    @staticmethod
    def write_to_disk_async(path:Path, df_dict:dict):
        logger.debug(f"writing to disk: {path}")
        pd.DataFrame(df_dict).to_csv(path, mode='x')

    def append_logs(self, log_struct_list:Collection[Union[CounterStruct, StatusStruct, FlowStruct]]):
        for struct in log_struct_list:
            if (isinstance(struct, CounterStruct)):
                self._append_counter(struct)
            elif isinstance(struct, StatusStruct):
                self._append_status(struct)
            else:
                assert isinstance(struct, FlowStruct)
                self._append_flow(struct)

        if self.write_to_disk(self.get_log_path(self.file_counter, False), force=False):
            self.file_counter += 1
