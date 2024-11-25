# from pyparsing import *
# hexadecimal = Regex("0x[0-9]+")

# vlan = Or([pyparsing_common.number, hexadecimal]) #TODO: check this is right
# port = Or([pyparsing_common.number, "\"" + Word(alphanums+'-'+'_') + "\""]) 

# priority = pyparsing_common.integer

# mac = Or([pyparsing_common.mac_address, pyparsing_common.mac_address + "/" + pyparsing_common.mac_address])
# ethertype = Or([pyparsing_common.integer, hexadecimal])

# ip = Combine(pyparsing_common.integer + "." + pyparsing_common.integer + "." + pyparsing_common.integer + "." + pyparsing_common.integer)
# ip_netmask = Or([pyparsing_common.url, Combine(ip + "/" + ip), Combine(ip + "/" + pyparsing_common.integer)])
        
# shorthand = Or([Literal("ip"), Literal("ipv4"), Literal("icmp"), Literal("icmp6"), Literal("tcp"), Literal("tcp6"), Literal("udp"), Literal("udp6"), Literal("sctp"), Literal("sctp6"), Literal("arp"), Literal("rarp"), Literal("mpls"), Literal("mplsm")])

# proto = Or([pyparsing_common.integer, hexadecimal])


# tos=pyparsing_common.integer

# dscp = pyparsing_common.integer

# ecn = pyparsing_common.integer

# ttl = pyparsing_common.integer

# mask = Or([pyparsing_common.integer, hexadecimal])

# flags = Or(pyparsing_common.integer, hexadecimal, )
# flag = Or(Literal("fin"), Literal("syn"), Literal("rst"), Literal("psh"), Literal("ack"), Literal("urg"), Literal("ece"), Literal("cwr"), Literal("ns"))

from ovs_dbg.ofparse.process import JSONProcessor
from ovs_dbg.ofparse.ofp import create_ofp_flow
from ovs.flow.ofp import OFPFlow
from ovs.flow.decoders import FlowEncoder
# p = JSONProcessor({}, create_ofp_flow)
# f = p.create_flow(" cookie=0x9700004c5eff71, duration=4.994s, table=0, n_packets=0, n_bytes=0, send_flow_rem priority=10,icmp,in_port=\"s1x2-eth1\",dl_src=aa:79:5d:f3:51:7e,dl_dst=0e:79:f7:2d:ed:52,nw_src=10.0.0.2,nw_dst=10.0.0.9,nw_tos=0,nw_ecn=0,icmp_type=0,icmp_code=0 actions=output:\"s1x2-eth5\"", 0)
# p.start_file("hi", "lol")
# p.process_flow(f, "lol")
# print(p.json_string())
import json
def flatten_dict(d:dict, key_header:str="")->dict:
    res_dict = {}
    print(type(d))
    for k, v in d.items():
        if isinstance(v, list):
            for idx, v_entry in enumerate(v):
                new_key = f"{key_header}_{k}{idx}" if key_header != "" else str(k)+str(idx)
                if isinstance(v_entry, dict):
                    for (v_entry_k, v_entry_v) in flatten_dict(v_entry).items():
                        res_dict[f"{new_key}_{v_entry_k}"] = v_entry_v
                else:
                    assert not isinstance(v_entry, list)
                    res_dict[new_key] = v_entry
        else:
            new_key = f"{key_header}_{k}" if key_header != "" else str(k) 
            if isinstance(v, dict):
                for (v_k, v_v) in flatten_dict(v).items():
                    res_dict[f"{new_key}_{v_k}"] = v_v
            else:
                res_dict[new_key] = v
    return res_dict


# p = JSONProcessor({}, create_ofp_flow)
# f = p.create_flow(" cookie=0x9700006724c679, duration=5.649s, table=0, n_packets=0, n_bytes=0, send_flow_rem priority=10,icmp,in_port=\"s1x2-eth1\",dl_src=aa:79:5d:f3:51:7e,dl_dst=66:d5:44:35:c4:60,nw_src=10.0.0.2,nw_dst=10.0.0.6,nw_tos=0,nw_ecn=0,icmp_type=8,icmp_code=0 actions=output:\"s1x2-eth3\"", 0)
# p.start_file("hi", "lol")
# p.process_flow(f, "lol")
# print(flatten_dict(json.loads(p.json_string())[0]))

# print(json.loads(json.dumps(OFPFlow(" cookie=0x9700006724c679, duration=5.649s, table=0, n_packets=0, n_bytes=0, send_flow_rem priority=10,icmp,in_port=\"s1x2-eth1\",dl_src=aa:79:5d:f3:51:7e,dl_dst=66:d5:44:35:c4:60,nw_src=10.0.0.2,nw_dst=10.0.0.6,nw_tos=0,nw_ecn=0,icmp_type=8,icmp_code=0 actions=output:\"s1x2-eth3\"").dict(), indent=4, cls=FlowEncoder)))

# json.dumps(
#                 [
#                     {"name": name, "flows": [flow.dict() for flow in flows]}
#                     for name, flows in self.flows.items()
#                 ],
#                 indent=4,
#                 cls=FlowEncoder,
#             )

# from telemetry_collection import FlowStruct
# print(FlowStruct(" cookie=0x9700006724c679, duration=5.649s, table=0, n_packets=0, n_bytes=0, send_flow_rem priority=10,icmp,in_port=\"s1x2-eth1\",dl_src=aa:79:5d:f3:51:7e,dl_dst=66:d5:44:35:c4:60,nw_src=10.0.0.2,nw_dst=10.0.0.6,nw_tos=0,nw_ecn=0,icmp_type=8,icmp_code=0 actions=output:\"s1x2-eth3\"").__dict__)
import pandas as pd
import asyncio
async def main():
    await pd.DataFrame({"hi":[1, 2, 3]}).to_csv("~/deez.csv")

asyncio.run(main())