"""
normal_traffic.py - iperf traffic for the media and heavy IoT devices.
Used by smart_home_topo.py (MQTT sensors live in mqtt_traffic.py).
"""

from mininet.log import info

from mqtt_traffic import LOG_FILE, BROKER_IP as CLOUD_IP

IPERF_PORT    = 5001                            # iperf's default port
IPERF_UDP_LOG = '/tmp/iperf_udp_server.log'     # per-burst jitter / loss seen by the cloud

# One profile per media device: how often, how much, how fast
UDP_PROFILES = {
    'camera':  dict(interval=(20, 60), size='200K', rate='2M'),
    'speaker': dict(interval=(15, 45), size='100K', rate='1M'),
}


def start_iperf_udp_server(cloud):
    """One iperf server on the cloud that receives every UDP burst."""
    info('*** Starting iperf UDP server on cloud\n')
    cloud.cmd(f'iperf -s -u -p {IPERF_PORT} -y C > {IPERF_UDP_LOG} 2>&1 &')


def start_udp_device(h, name, profile, log_file=LOG_FILE):
    """One media IoT device that sends a UDP burst to the cloud at random intervals."""
    lo, hi = profile['interval']
    size = profile['size']
    rate = profile['rate']
    cmd = (
        f'( sleep $(( RANDOM % 5 )); '
        f'while true; do '
        f'START=$(date +%s.%N); '
        f'iperf -c {CLOUD_IP} -p {IPERF_PORT} -u -n {size} -b {rate} '
        f'> /dev/null 2>&1; '
        f'echo "$START,{name},udp,{size},burst" >> {log_file}; '
        f'sleep $(( {lo} + RANDOM % ({hi}-{lo}+1) )); '
        f'done ) &'
    )
    h.cmd(cmd)


def start_normal_traffic(hosts, cloud):
    """Receiver on the cloud first, then the media devices."""
    info('*** Starting normal (iperf) traffic\n')
    cloud.cmd(f'rm -f {IPERF_UDP_LOG}')               # fresh log each run
    start_iperf_udp_server(cloud)
    for name, profile in UDP_PROFILES.items():
        start_udp_device(hosts[name], name, profile)


def stop_normal_traffic(hosts, cloud):
    """Stop every background job on the IoT devices and the cloud."""
    info('*** Stopping normal (iperf) traffic\n')
    for h in list(hosts.values()) + [cloud]:
        h.cmd('kill $(jobs -p) 2>/dev/null')