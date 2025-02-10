# Input Validation

Codebase for exploring feasibility of input validation.

## Hardware Requirements
☐ Check if you can run paint <br />
☐ Potato <br />
☐ Decent <br />
☐ Fast <br />
☐ Rich boi <br />
☑ [Ask NASA if they have a spare computer :(](https://www.nas.nasa.gov/hecc/support/system_status.html)

## How to run (in google cloud):
1. Setup the `input_validation` experiment and configurations:
    1. In your desired directory, `git clone https://github.com/akrentsel/input-validation.git`
    2. In that directory, modify configuration files `log_config.yaml` and `experiment_config.yaml`; **you will probably need to do this**. 
        - In particular, pay attention to the following in `experiment_config.yaml`:
            - `telemetry_config/base_log_dir`
            - `telemetry_config/error_log_dir`
            - `experiment_config/logging_config_filepath` (set this to the path of `log_config.yaml`)
        - And to the following in `log_config.yaml`:
            - `handlers/*/filename`
    3. Using the same `pip` binary you will be running in `sudo` mode, run `cd input-validation; {path to pip binary} install -r requirements.txt`
2. Start ONOS controller: 
    1. in one terminal, run `sudo docker run -t -p 8181:8181 -p 8101:8101 -p 5005:5005 -p 830:830 --name onos onosproject/onos`; wait for a status message of the form `Updated node {IP address} state to READY` before proceeding (usually that IP is 172.17.0.2); *do not quit or exit this terminal, or use -d flag to start the container in detached mode*
    2. in another terminal, using the IP address seen in the above status message, run `ssh -p 8101 karaf@{IP address}`, and use the default password `karaf`; this should open an ONOS karaf CLI interface.
    3. Remember that IP address; you will need it later to run the experiment.
3. Configure ONOS controller:
    1. in the ONOS karaf CLI interface from the previous step, run the following:
        ```
        app activate org.onosproject.openflow
        app activate org.onosproject.ofagent
        app activate org.onosproject.reactive-routing
        app activate org.onosproject.fibinstaller
        app activate org.onosproject.fwd
        ```

        by doing this, we activate the following applications:
        - `org.onosproject.openflow` (needed for processing OpenFlow messages)
        - `org.onosproject.ofagent` (i'm not sure what this does)
        - `org.onosproject.reactive-routing` (needed for using IP-based flow routing)
        - `org.onosproject.fibinstaller` (i'm not sure what this does)
        - `org.onosproject.fwd` (needed for installing flow tables / flow programming)
    3. Wait for the previous step to complete; then, run the following in that same CLI interface:
        ```
        cfg set org.onosproject.fwd.ReactiveForwarding ipv6Forwarding true
        cfg set org.onosproject.fwd.ReactiveForwarding matchIcmpFields true
        cfg set org.onosproject.fwd.ReactiveForwarding matchIpv4Address true
        cfg set org.onosproject.fwd.ReactiveForwarding matchIpv4Dscp true
        cfg set org.onosproject.fwd.ReactiveForwarding matchIpv6Address true
        cfg set org.onosproject.fwd.ReactiveForwarding matchIpv6FlowLabel true
        cfg set org.onosproject.fwd.ReactiveForwarding matchTcpUdpPorts true
        ```
        **Make sure there are no messages of the form `... is not configured`; if they appear, rerun these commands as many times as necessary.**
    4. After this, can `logout` of the karaf interface.
4. Check that IPv6 is disabled on the controller; if not:
    1. append the following to `/etc/sysctl.conf`:
        ```
        net.ipv6.conf.all.disable_ipv6 = 1
        net.ipv6.conf.default.disable_ipv6 = 1
        net.ipv6.conf.lo.disable_ipv6 = 1
        ```
    2. run `sudo sysctl -p` to make changes take effect.
5. Run the experiment: `cd ~/input-validation; sudo {path to python binary} experiment_main.py --config_path={your path to experiment config file} --ip={IP address from controller as seen earlier} --port=6653`.
    - If needed, clear the directory where experiment outputs are stored, and reset the mininet environment with `sudo mn -c`
    - If needed, e.g. due to `python not found` error, run `source ~/.bashrc`
    - If python not installed, install `miniconda3`

## Installation instructions (in google cloud):
1. `sudo apt-get install mininet`
2. `sudo docker pull onosproject/onos`
3. disable IPv6:
    1. append the following to `/etc/sysctl.conf`:
        ```
        net.ipv6.conf.all.disable_ipv6 = 1
        net.ipv6.conf.default.disable_ipv6 = 1
        net.ipv6.conf.lo.disable_ipv6 = 1
        ```
    2. run `sudo sysctl -p` to make changes take effect.
