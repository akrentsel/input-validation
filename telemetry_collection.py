
from typing import Union
from mininet.node import Host
from mininet.net import Mininet
from collections.abc import Collection
from asyncio import get_event_loop
import json
from threading import Lock
from pathlib import Path
import asyncio
from ovs.flow.ofp import OFPFlow
from ovs.flow.decoders import FlowEncoder
import pandas as pd
from experiment import ExperimentControlBlock

class CounterStruct():
    def __init__(self, timestamp:float, switch_name:str, interface_name:str, dir:str, stat_type:str, value:int):
        self.timestamp = timestamp
        self.switch_name = switch_name
        self.interface_name = interface_name
        self.dir = dir
        self.stat_type = stat_type
        self.value = value

class StatusStruct():
    def __init__(self, timestamp:float, switch_name:str, interface_name:str, status:bool):
        self.timestamp = timestamp
        self.switch_name = switch_name
        self.interface_name = interface_name
        self.status = status

class FlowStruct():
    def __init__(self, timestamp:float, switch_name:str, flow_cli_output:str):
        self.timestamp = timestamp
        self.switch_name = switch_name
        self.match_entries = {}
        self.action_entries = {}
        self.info_entries = {}

        ofp_parsing:dict = json.loads(json.dumps(OFPFlow(flow_cli_output).dict(), indent=4, cls=FlowEncoder))
        if "match" in ofp_parsing:
            self.match_entries = FlowStruct.flatten_dict(ofp_parsing['match'])
        if "actions" in ofp_parsing:
            self.action_entries = FlowStruct.flatten_list(ofp_parsing['actions'], 'action')
        if "info" in ofp_parsing:
            self.info_entries = FlowStruct.flatten_dict(ofp_parsing['info'])

        self.interface_name = self.info_entries['']

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


class TelemetryControlBlock():
    def __init__(self, mininet:Mininet, log_dir:Path):
        self.host_manager_map:dict = {}
        self.host_list:Collection[Host] = list(mininet.hosts)
        self.kill_signal:bool = False # TODO: implement graceful termination...
        self.lock:Lock = Lock()
        self.log_dir:Path = log_dir

        self.host_list = list(mininet.hosts)
        for host in mininet.hosts:
            # self.host_manager_map[host] = 
            pass



    def run_simulation(self):
        loop = get_event_loop()
        loop.call_later()


class HostTelemetryManager():
    MAX_NUM_ROWS = 1000
    def __init__(self, host:Host, experiment_control_block:ExperimentControlBlock, telemetry_control_block:TelemetryControlBlock, log_name_prefix:str, max_rows:int=MAX_NUM_ROWS, min_store_time:int=600):
        self.filename_prefix = log_name_prefix
        self.file_counter = 0
        self.experiment_control_block:ExperimentControlBlock = experiment_control_block
        self.telemetry_control_block:TelemetryControlBlock = telemetry_control_block
        self.host:Host = host
        self.log_struct = TelemetryLogStruct()
        self.lock:Lock = Lock()
        self.min_store_time = min_store_time


    async def append_logs(self, log_struct_list:Collection[Union[CounterStruct, StatusStruct, FlowStruct]]):
        self.lock.acquire()
        for struct in log_struct_list:
            if (isinstance(struct, CounterStruct)):
                self.log_struct.append_counter(struct)
            elif isinstance(struct, StatusStruct):
                self.log_struct.append_status(struct)
            else:
                assert isinstance(struct, FlowStruct)
                self.log_struct.append_flow(struct)

        if self.log_struct.write_to_disk(self.telemetry_control_block.log_dir / self.filename_prefix+int(self.file_counter), self.experiment_control_block.get_experiment_timestamp() - self.min_store_time):
            self.file_counter += 1
        self.lock.release()

        
class TelemetryLogStruct():
    MIN_WRITE_LEN = 500
    def __init__(self):
        self.num_entries = 0

        # common
        self.timestamp_list = []
        # self.hosts = []
        self.router_name_list = []
        self.telemetry_type_list = []

        # interface counter telemetry
        self.interface_name_list = []
        self.direction_list = []
        self.counter_type_list = []
        self.counter_val_list = []

        # flow table telemetry
        self.match_dict_list = {}
        self.action_dict_list = {}
        self.info_dict_list = {}

    def append_counter(self, counter_struct:CounterStruct):
        self.timestamp_list.append(counter_struct.timestamp)
        self.router_name_list.append(counter_struct.switch_name)
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
    def append_status(self, status_struct:StatusStruct):
        self.timestamp_list.append(status_struct.timestamp)
        self.router_name_list.append(status_struct.switch_name)
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
    
    def append_flow(self, flow_struct:FlowStruct):
        self.num_entries += 1
        self.timestamp_list.append(flow_struct.timestamp)
        self.router_name_list.append(flow_struct.switch_name)
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

    def write_to_disk(self, path:Path, timestamp_before:int=10e10)->bool:
        idx_before = self.get_idx_before(timestamp_before)
        if (idx_before < TelemetryLogStruct.MIN_WRITE_LEN - 1):
            return False
        df_dict = {"timestamp": self.timestamp_list[:idx_before], "router_name": self.router_name_list[:idx_before], "telemetry_type":self.telemetry_type_list[:idx_before], "interface_name": self.interface_name_list[:idx_before], "counter_direction": self.direction_list[:idx_before], "counter_type": self.counter_type_list[:idx_before], "counter_val": self.counter_val_list[:idx_before]}
        for dict_list in [self.info_dict_list, self.match_dict_list, self.action_dict_list]:
            for k, v in dict_list.items():
                df_dict[k] = v[:idx_before]

        pd.DataFrame(df_dict).to_csv(path)

        self.timestamp_list = self.timestamp_list[idx_before:]
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


