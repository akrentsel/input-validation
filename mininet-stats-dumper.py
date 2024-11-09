"""
This script simulates a simple network topology using Mininet and generates network traffic traces.

The script performs the following main tasks:
1. Creates a network topology with two hosts (h1, h2) connected through two switches (s1, s2).
2. Generates variable network traffic between the hosts using iperf.
3. Collects interface counter statistics from the switches at regular intervals.
4. Collates the collected statistics into a single CSV file for analysis.

Key components:
- create_network(): Sets up the Mininet network topology.
- generate_traffic(): Simulates variable network traffic between hosts.
- dump_counters(): Collects interface statistics from switches.
- parse_ovs_dump_ports(): Parses the output of 'ovs-ofctl dump-ports' command.
- construct_csv_rows(): Formats parsed data into CSV rows.
- collate_logs(): Combines individual switch logs into a single CSV file.
- run_simulation(): Orchestrates the entire simulation process.

The script uses threading to simultaneously generate traffic and collect statistics,
providing a realistic simulation of network behavior and data collection.

Usage:
    python mininet_traces.py

Output:
    - Individual CSV files for each switch containing interface statistics.
    - A collated CSV file ('collated_logs.csv') combining all switch statistics.
"""

# Import necessary libraries
from mininet.net import Mininet
from mininet.node import OVSController
from mininet.log import setLogLevel, info
from mininet.link import TCLink
import time
import random
import threading
import csv
import re
from datetime import datetime, timedelta

def create_network():
    """
    Create and return a Mininet network with two hosts and two switches.

    Returns:
        Mininet: A Mininet network object with the specified topology.
    """
    net = Mininet(controller=OVSController, link=TCLink)
    
    # Add hosts and switches
    h1 = net.addHost('h1')
    h2 = net.addHost('h2')
    s1 = net.addSwitch('s1')
    s2 = net.addSwitch('s2')
    
    # Add links
    net.addLink(h1, s1)
    net.addLink(s1, s2)
    net.addLink(s2, h2)
    
    # Add controller
    net.addController('c0')
    
    return net
def generate_traffic(h1, h2, duration=100, period=10):
    """
    Generate traffic between two hosts using iperf.

    Args:
        h1 (Host): Source host.
        h2 (Host): Destination host.
        duration (int): Total duration of traffic generation in seconds.
        period (int): Interval between rate changes in seconds.

    This function simulates variable network traffic by randomly changing the
    traffic rate every 'period' seconds, creating a dynamic and realistic
    network load scenario.
    """
    info("*** Generating traffic\n")
    
    # Start iperf server on h2
    h2.cmd("iperf -s &")
    
    # Print a warning if period is less than 5 seconds
    if period < 5:
        info("Warning: Period is less than 5 seconds. This may lead to less accurate or stable measurements.\n")
    
    for i in range(0, duration, period):
        rate = random.randint(50, 200)  # Random rate between 50-200 Mbps
        info(f"Time {i}: New traffic rate: {rate} Mbps\n")
        
        # Run iperf client and capture output
        iperf_output = h1.cmd(f"iperf -c {h2.IP()} -t {period} -b {rate}M")
        
        # Parse and log iperf output (you may want to implement a separate function for this)
        # For example:
        # log_iperf_results(iperf_output)
        print(f'iperf_output: {iperf_output}')

    # Stop iperf server on h2
    h2.cmd("killall iperf")

# Remember to call start_monitoring(net) after net.start() in your main function
        
def parse_ovs_dump_ports(output):
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
    # Regex patterns to match lines for ports
    port_pattern = r'port\s+("?[\w-]+"?):'  # Match port names with or without quotes
    rx_pattern = r'rx pkts=(\d+), bytes=(\d+), drop=(\d+), errs=(\d+), frame=(\d+), over=(\d+), crc=(\d+)'
    tx_pattern = r'tx pkts=(\d+), bytes=(\d+), drop=(\d+), errs=(\d+), coll=(\d+)'
    
    parsed_data = {}

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
                parsed_data[current_port]["rx"] = {
                    "pkts": int(rx_match.group(1)),
                    "bytes": int(rx_match.group(2)),
                    "drop": int(rx_match.group(3)),
                    "errs": int(rx_match.group(4)),
                }

            # Match the TX line
            tx_match = re.search(tx_pattern, line)
            if tx_match:
                parsed_data[current_port]["tx"] = {
                    "pkts": int(tx_match.group(1)),
                    "bytes": int(tx_match.group(2)),
                    "drop": int(tx_match.group(3)),
                    "errs": int(tx_match.group(4)),
                }
    return parsed_data

def construct_csv_rows(parsed_data, timestamp, switch_name):
    """
    Construct CSV rows from parsed port statistics data.

    Args:
        parsed_data (dict): Parsed port statistics data.
        timestamp (int): Timestamp for the data.
        switch_name (str): Name of the switch.

    Returns:
        list: List of CSV rows, each containing statistics for a specific port and direction.
    """
    entries = []
    for port, data in parsed_data.items():
        interface_name = port if port != 'LOCAL' else 'lo'
        for direction in ['rx', 'tx']:
            for stat_type, value in data[direction].items():
                entries.append([timestamp, switch_name, interface_name, direction, stat_type, value])
    return entries

def dump_counters(s, switch_name, global_start_time,duration=100, period=3, offset=0):
    """
    Dump interface counters for a switch and write them to a CSV file.

    Args:
        s (Switch): The switch object.
        switch_name (str): Name of the switch.
        global_start_time (float): Global start time of the simulation.
        duration (int): Duration of the counter dumping in seconds.
        period (int): Interval between counter dumps in seconds.
        offset (float): Offset time before starting the counter dump.
    """
    info(f"*** Dumping interface counters for {switch_name}\n")
    end_time = global_start_time + timedelta(seconds=duration)
    
    with open(f'counter_dumps_{switch_name}.csv', 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(['timestamp_ms', 'router_name', 'interface_name', 'dir', 'type', 'val'])
        
        # Sleep for the offset time (to be able to offset the start of the measurement on each switch)
        time.sleep(offset)
        
        while datetime.now() < end_time:
            output = s.cmd('ovs-ofctl dump-ports', switch_name, '-O', 'OpenFlow13')
            current_time = datetime.now()
            timestamp = int((current_time - global_start_time).total_seconds() * 1000)
            parsed_data = parse_ovs_dump_ports(output)
            entries = construct_csv_rows(parsed_data, timestamp, switch_name)
            
            for entry in entries:
                csvwriter.writerow(entry)
                print(f"Adding row for {switch_name}: {entry}")
        
            # Sleep for the remaining time in the period
            runtime = (datetime.now() - current_time).total_seconds()
            sleep_time = period - runtime
            if sleep_time > 0:
                print(f"Sleeping for {sleep_time} seconds for {switch_name}")
                time.sleep(sleep_time)
            else:
                print(f"Warning: counter dump period [{period}] for {switch_name} is shorter than the duration of the iperf run [{runtime}]")
                
def collate_logs(switch_names):
    """
    Collate all created logs into a single CSV log file.

    Args:
        switch_names (list): List of switch names to collate logs for.
    """
    # Define the expected log files based on switch names
    log_files = [f'counter_dumps_{switch}.csv' for switch in switch_names]
    
    # Prepare the output file
    output_file = 'collated_logs.csv'
    
    # Initialize a list to store all rows and the header
    all_rows = []
    header = None
    
    # Read all log files
    for log_file in log_files:
        with open(log_file, 'r') as f:
            reader = csv.reader(f)
            if header is None:
                header = next(reader)  # Save the header from the first file
            else:
                next(reader)  # Skip header for subsequent files
            all_rows.extend(list(reader))
    
    # Sort all rows by timestamp_ms (first column)
    all_rows.sort(key=lambda x: int(x[0]))
    
    # Write the collated data to a new CSV file
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)  # Write the original header
        writer.writerows(all_rows)

    print(f"Collated logs have been written to {output_file}")

def run_simulation():
    """
    Run the main simulation, setting up the network, generating traffic, and dumping counters.
    """
    DURATION = 100 # half an hour
    MEASUREMENT_PERIOD = 3
    RATE_CHANGE_PERIOD = 10
    
    # Use a single `global_start_time` for all switches to represent assuming switch clocks are synchronized across the network.
    global_start_time = datetime.now()
    
    
    setLogLevel('info')
    net = create_network()
    
    try:
        net.start()
        h1, h2 = net.get('h1', 'h2')
        s1, s2 = net.get('s1', 's2')

        # Start traffic generation and counter dumping in separate threads
        traffic_thread = threading.Thread(target=generate_traffic, args=(h1, h2, DURATION, RATE_CHANGE_PERIOD))
        
        # Offset the start of the counter dump for each switch by a random amount up to the measurement period
        s1_offset = random.uniform(0, MEASUREMENT_PERIOD)
        counters_thread_s1 = threading.Thread(target=dump_counters, args=(s1, 's1', global_start_time, DURATION, MEASUREMENT_PERIOD, s1_offset))
        s2_offset = random.uniform(0, MEASUREMENT_PERIOD)
        counters_thread_s2 = threading.Thread(target=dump_counters, args=(s2, 's2', global_start_time, DURATION, MEASUREMENT_PERIOD, s2_offset))

        # Start the threads
        traffic_thread.start()
        counters_thread_s1.start()
        counters_thread_s2.start()

        # Wait for threads to finish
        traffic_thread.join()
        counters_thread_s1.join()
        counters_thread_s2.join()

    finally:
        net.stop()
    
    # Call the collate_logs function after the simulation with the switch names
    collate_logs(['s1', 's2'])
    print("All done, have a nice day!")

if __name__ == '__main__':
    run_simulation()
