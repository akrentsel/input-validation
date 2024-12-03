
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

logger = logging.getLogger("telemetry_collection")
class TelemetryStruct(object):
    def __init__(self, timestamp:float, switch_name:str, errors_applied:Collection[str]):
        self.timestamp = timestamp
        self.switch_name = switch_name
        self.errors_applied = list(errors_applied)

    def _delay(self, new_timestamp):
        new_copy = self._copy()
        assert new_timestamp > self.timestamp, f"new timestamp {new_timestamp} must be greater than current timestamp {self.timestamp}"
        new_copy.timestamp = new_timestamp

        new_copy.errors_applied.append(f"DELAY (old time: {self.timestamp})")
        return new_copy

class CounterStruct(TelemetryStruct):
    def __init__(self, timestamp:float, switch_name:str, interface_name:str, dir:str, stat_type:str, value:int, errors_applied:Collection[str]=[]):
        super(CounterStruct, self).__init__(timestamp, switch_name, errors_applied)
        self.interface_name = interface_name
        self.dir = dir
        self.stat_type = stat_type
        self.value = value
    
    def _copy(self):
        return CounterStruct(self.timestamp, self.switch_name, 
        self.interface_name, self.dir, self.stat_type, self.value, self.errors_applied)

    def _drop(self):
        corrupt_struct = self._copy()
        corrupt_struct.value = None
        corrupt_struct.errors_applied.append(f"DROP")
        return corrupt_struct
    
    def _multiply(self, factor):
        corrupt_struct = self._copy()
        corrupt_struct.value *= factor
        corrupt_struct.errors_applied.append(f"SPIKE (factor={factor})")
        return corrupt_struct

    def _zero(self):
        corrupt_struct = self._copy()
        corrupt_struct.value = 0
        corrupt_struct.errors_applied.append(f"ZERO")
        return corrupt_struct

class StatusStruct(TelemetryStruct):
    def __init__(self, timestamp:float, switch_name:str, interface_name:str, status:bool, errors_applied:Collection[str]=[]):
        super(StatusStruct, self).__init__(timestamp, switch_name, errors_applied)
        self.interface_name = interface_name
        self.status = status

    def _copy(self):
        return StatusStruct(self.timestamp, self.switch_name, self.interface_name, self.status, self.errors_applied)

    def _drop(self):
        corrupt_struct = self._copy()
        corrupt_struct.status = None
        corrupt_struct.errors_applied.append(f"DROP")
        return corrupt_struct
    
    def _flip(self):
        corrupt_struct = self._copy()
        corrupt_struct.status = not corrupt_struct.status
        corrupt_struct.errors_applied.append(f"FLIP")
        return corrupt_struct

class FlowStruct(TelemetryStruct):
    def __init__(self, timestamp:float, switch_name:str, flow_cli_output:str, errors_applied:Collection[str]=[]):
        super(FlowStruct, self).__init__(timestamp, switch_name, errors_applied)
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

    def _copy(self):
        return FlowStruct(self.timestamp, self.switch_name, self.original, self.errors_applied)
    def _drop(self):
        corrupt_struct = self.copy()
        for ofp_dict in [corrupt_struct.match_entries, corrupt_struct.action_entries, corrupt_struct.info_entries]:
            for k in ofp_dict.keys():
                ofp_dict[k] = None

        
        corrupt_struct.errors_applied.append(f"DROP")
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