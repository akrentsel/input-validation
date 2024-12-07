# Input Validation

Codebase for exploring feasibility of input validation.

## Hardware Requirements
☐ Check if you can run paint
☐ Potato
☐ Decent
☐ Fast
☐ Rich boi
☑ [Ask NASA if they have a spare computer :(](https://www.nas.nasa.gov/hecc/support/system_status.html)

## Installation instructions (via VM):
1. Follow Mininet VM installation instructions [here (as option 1)](https://mininet.org/download/)
    - In particular, the [VM setup notes](https://mininet.org/vm-setup-notes/) are important to follow.
    - Personal preference: VMWare as virtualization system; **Ubuntu 20.04** as the Mininet VM image version.
2. Configure the VM to have much more processors and memory (trust me, you will need this)
    - my settings: 2 processors, 8 cores per processor; 16GB of memory.
3. Also, enlarge the VM disk size (e.g. to 32 GB); not sure if this is needed but it may be.
    - you may need to enlarge the partition within the Mininet VM by using [Gparted](https://gparted.org/) in a Xterm-forwarding-enabled SSH session.
4. [Install Miniconda](https://docs.anaconda.com/miniconda/install/) in the Mininet VM, **making sure to select the option to modify PATH (or .bashrc, I can't remember)**
5. Now, install the ONOS controller in the Mininet VM. 
    - [**Install the dependencies needed for ONOS installation**](https://github.com/opennetworkinglab/onos?tab=readme-ov-file#build-onos-from-source)
        - or else, ONOS won't build properly!
    - Then, [build ONOS from source](https://github.com/opennetworkinglab/onos?tab=readme-ov-file#build-onos-from-source).
    - (note: ONOS does have pre-built images, but I couldn't get them to run in the VM. So, we build from source instead!)
6. Clone this repo and install requirements:
    ```
    cd ~
    git clone https://github.com/akrentsel/input-validation.git
    cd input-validation
    pip install -r requirements.txt
    ```

## How to run:
1. Modify configuration files `log_config.yaml` and `experiment_config.yaml` as needed
2. Start ONOS controller:
    1. SSH into mininet VM, open CLI window and run `cd ~/onos; bazel run onos-local debug`; wait for a status message of the form `Updated node 127.0.0.1 state to READY` before proceeding.
    2. SSH into in mininet VM, open another CLI window and `cd ~/onos; ./tools/test/bin/onos localhost`; this should open an ONOS CLI interface.
3. Configure ONOS controller, open its topology GUI view, and enable openflow/routing applications: 
    1. In mininet VM CLI, run `ifconfig -a` to get the IP address for host-only interface; in browser of choice (can be on host computer), go to `<ip address>:8181` and login with credentials: username=`onos`, password=`rocks`; the network topology can be viewed in a GUI by going to the `Topology` tab in the dropdown menu.
    2. In the ONOS CLI interface, run the following:
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
    3. In the ONOS CLI interface from 2.(2), run the following:
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
4. Run the experiment: `cd ~/input-validation; sudo python experiment_main.py`.
    - If needed, clear the directory where experiment outputs are stored, and reset the mininet environment with `sudo mn -c`
    - 