from subprocess import Popen, PIPE
import os
if os.geteuid() != 0:
    exit("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")
Popen(['ovs-ofctl', 'dump-flows', 's1x2', '-O', 'OpenFlow13'], stdin=PIPE, stderr=PIPE, text=True).wait()