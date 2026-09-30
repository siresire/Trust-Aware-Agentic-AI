"""
normal_traffic.py - iperf traffic for the media and heavy IoT devices.
Used by smart_home_topo.py (MQTT sensors live in mqtt_traffic.py).
"""

from mininet.log import info

from mqtt_traffic import LOG_FILE, BROKER_IP as CLOUD_IP, device_seed

IPERF_PORT    = 5001                            # iperf's default port
IPERF_UDP_LOG = '/tmp/iperf_udp_server.log'     # per-burst jitter / loss seen by the cloud
IPERF_TCP_LOG = '/tmp/iperf_tcp_server.log'     # per-transfer results seen by the cloud

# One profile per media device: how often, how much (KB range), how fast
UDP_PROFILES = {
    'camera':  dict(interval=(20, 60), size=(100, 400), rate='2M'),
    'speaker': dict(interval=(15, 45), size=(30, 200),  rate='1M'),
}

TCP_PROFILES = {
    'phone':  dict(interval=(5, 30), size=(100, 1000), rate='2M'),
    'laptop': dict(interval=(5, 20), size=(200, 2000), rate='3M'),
}

STREAM_PROFILES = {
    'tv': dict(rate='2M', duration=3600),
}


def start_iperf_udp_server(cloud):
    """One iperf server on the cloud that receives every UDP burst."""
    info('*** Starting iperf UDP server on cloud\n')
    cloud.cmd(f'iperf -s -u -p {IPERF_PORT} -y C > {IPERF_UDP_LOG} 2>&1 &')


def start_iperf_tcp_server(cloud):
    """One iperf server on the cloud that receives every TCP transfer and stream."""
    info('*** Starting iperf TCP server on cloud\n')
    cloud.cmd(f'iperf -s -p {IPERF_PORT} -y C > {IPERF_TCP_LOG} 2>&1 &')


def start_burst_device(h, name, profile, proto, seed, log_file=LOG_FILE):
    """One IoT device that sends UDP or TCP bursts of random (seeded) size."""
    lo, hi = profile['interval']
    s_lo, s_hi = profile['size']
    rate = profile['rate']
    udp_flag = '-u' if proto == 'udp' else ''
    cmd = (
        f'( RANDOM={seed}; sleep $(( RANDOM % 5 )); '
        f'while true; do '
        f'SIZE=$(( {s_lo} + RANDOM % ({s_hi}-{s_lo}+1) ))K; '
        f'START=$(date +%s.%N); '
        f'iperf -c {CLOUD_IP} -p {IPERF_PORT} {udp_flag} -n $SIZE -b {rate} '
        f'> /dev/null 2>&1; '
        f'echo "$START,{name},{proto},$SIZE,burst" >> {log_file}; '
        f'sleep $(( {lo} + RANDOM % ({hi}-{lo}+1) )); '
        f'done ) &'
    )
    h.cmd(cmd)


def start_stream_device(h, name, profile, log_file=LOG_FILE):
    """One device with a continuous TCP stream (restarts if it ever ends)."""
    rate = profile['rate']
    duration = profile['duration']
    cmd = (
        f'( while true; do '
        f'echo "$(date +%s.%N),{name},tcp,{rate},sustained-start" >> {log_file}; '
        f'iperf -c {CLOUD_IP} -p {IPERF_PORT} -t {duration} -b {rate} '
        f'> /dev/null 2>&1; '
        f'done ) &'
    )
    h.cmd(cmd)


def start_normal_traffic(hosts, cloud, seed):
    """Receivers on the cloud first, then every iperf device (each with its own seed)."""
    info(f'*** Starting normal (iperf) traffic (seed={seed})\n')
    cloud.cmd(f'rm -f {IPERF_UDP_LOG} {IPERF_TCP_LOG}')   # fresh logs each run
    start_iperf_udp_server(cloud)
    start_iperf_tcp_server(cloud)
    for name, profile in UDP_PROFILES.items():
        start_burst_device(hosts[name], name, profile, 'udp', device_seed(seed, name))
    for name, profile in TCP_PROFILES.items():
        start_burst_device(hosts[name], name, profile, 'tcp', device_seed(seed, name))
    for name, profile in STREAM_PROFILES.items():
        start_stream_device(hosts[name], name, profile)


def stop_normal_traffic(hosts, cloud):
    """Stop every background job on the IoT devices and the cloud."""
    info('*** Stopping normal (iperf) traffic\n')
    for h in list(hosts.values()) + [cloud]:
        h.cmd('kill $(jobs -p) 2>/dev/null')