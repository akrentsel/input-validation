from pyparsing import *
LQUOTE, RQUOTE = map(Literal, "{}")

# test_string = "\""
# print(len(test_string))

# pyparsing_common.number.run_tests('''
#     # any int or real number, returned as the appropriate type
#     0x3235
#     ''')

hexa = Literal("0x") + pyparsing_common.hex_integer
print(hexa.parse_string("0x235"))

ip = pyparsing_common.integer + Literal(".") + pyparsing_common.integer + Literal(".") + pyparsing_common.integer + Literal(".") + pyparsing_common.integer
ip.set_results_name("IP", list_all_matches=True)
print(ip("ip").parse_string("192.168.23.52").as_dict())

# mac = Or(pyparsing_common.mac_address, pyparsing_common.mac_address + Literal("/") + pyparsing_common.mac_address)
# print(mac("mac").parse_string("01:00:00:00:00:00/01:00:00:00:00:00",parse_all=True))

ip_netmask= Or([pyparsing_common.url, Combine(ip + "/" + ip), Combine(ip + "/" + pyparsing_common.integer)])
print(ip_netmask.parse_string("192.126.13.252/23"))