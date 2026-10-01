"""
network_monitor.py - measures every IoT device and the router while the network runs.
Throughput from byte counters; RTT, jitter and loss from ping to the cloud;
TCP internals (ss -ti) for the TCP devices. Used by smart_home_topo.py.
"""

import os
import shutil

from mininet.log import info

METRICS_DIR = '/tmp/network_metrics'   # one log file per device / router side
INTERVAL = 2                           # seconds between measurements
TCP_DIR = '/tmp/tcp_metrics'             # one TCP log per TCP device
TCP_HOSTS = ['phone', 'laptop', 'tv']    # devices whose traffic to the cloud is TCP

_monitor_pids = []                     # (node, pid) of every loop we start, to stop exactly those


def start_device_monitor(node, label, iface, ping_dst=None, interval=INTERVAL,
                         metrics_dir=METRICS_DIR):
    """Every `interval` s, log throughput and (if ping_dst is given) RTT, jitter, loss."""
    log = f'{metrics_dir}/{label}.log'
    tmp = f'{metrics_dir}/{label}.ping'          # this loop's latest raw ping output
    with open(log, 'w') as f:
        f.write('timestamp,device,rx_kbps,tx_kbps,rtt_ms,jitter_ms,loss_pct\n')

    if ping_dst:
        ping_start = (
            f'ping -c 3 -i 0.2 -W 1 {ping_dst} > {tmp} 2>&1 & '
            f'PING_PID=$!; '
        )
        ping_read = (
            f'wait $PING_PID; '
            f'LOSS=$(grep -oP "[0-9.]+(?=% packet loss)" {tmp}); '
            f'RTT_LINE=$(grep rtt {tmp}); '
            f'RTT_AVG=$(echo "$RTT_LINE" | cut -d/ -f5); '
            f'RTT_MDEV=$(echo "$RTT_LINE" | cut -d/ -f7); '
            f'RTT_MDEV=${{RTT_MDEV% ms}}; '
        )
    else:
        ping_start = ''
        ping_read = ''

    stats = f'/sys/class/net/{iface}/statistics'
    cmd = (
        f'( while true; do '
        f'T1=$(date +%s%N); '
        f'RX1=$(cat {stats}/rx_bytes); TX1=$(cat {stats}/tx_bytes); '
        f'{ping_start}'
        f'sleep {interval}; '
        f'{ping_read}'
        f'T2=$(date +%s%N); '
        f'RX2=$(cat {stats}/rx_bytes); TX2=$(cat {stats}/tx_bytes); '
        f'MS=$(( (T2-T1)/1000000 )); '
        f'RX_KBPS=$(( (RX2-RX1)*8/MS )); '
        f'TX_KBPS=$(( (TX2-TX1)*8/MS )); '
        f'echo "$(date +%s.%N),{label},$RX_KBPS,$TX_KBPS,'
        f'${{RTT_AVG:-NA}},${{RTT_MDEV:-NA}},${{LOSS:-NA}}" >> {log}; '
        f'done ) &'
    )
    node.cmd(cmd)
    pid = node.cmd('echo $!').strip()
    _monitor_pids.append((node, pid))


def start_tcp_monitor(node, label, dst, interval=INTERVAL, tcp_dir=TCP_DIR):
    """Every `interval` s, log TCP's internal state for this device's connection to the cloud."""
    log = f'{tcp_dir}/{label}.log'
    with open(log, 'w') as f:
        f.write('timestamp,device,conns,cwnd,ssthresh,srtt_ms,retrans_total,unacked\n')

    flt = f'state established dst {dst} dport = :5001'
    cmd = (
        f'( while true; do '
        f'CONNS=$(ss -tn {flt} | tail -n +2 | wc -l); '
        f'STATS=$(ss -tin {flt} | grep -m1 cwnd); '
        f'CWND=$(echo "$STATS" | grep -oP "\\bcwnd:\\K[0-9]+"); '
        f'SSTHRESH=$(echo "$STATS" | grep -oP "\\bssthresh:\\K[0-9]+"); '
        f'SRTT=$(echo "$STATS" | grep -oP "\\brtt:\\K[0-9.]+"); '
        f'RETRANS=$(echo "$STATS" | grep -oP "\\bretrans:[0-9]+/\\K[0-9]+"); '
        f'UNACKED=$(echo "$STATS" | grep -oP "\\bunacked:\\K[0-9]+"); '
        f'if [ "$CONNS" -gt 0 ]; then '
        f'RETRANS=${{RETRANS:-0}}; UNACKED=${{UNACKED:-0}}; fi; '
        f'echo "$(date +%s.%N),{label},$CONNS,${{CWND:-NA}},${{SSTHRESH:-NA}},'
        f'${{SRTT:-NA}},${{RETRANS:-NA}},${{UNACKED:-NA}}" >> {log}; '
        f'sleep {interval}; '
        f'done ) &'
    )
    node.cmd(cmd)
    pid = node.cmd('echo $!').strip()
    _monitor_pids.append((node, pid))


def start_network_monitoring(hosts, router, cloud, interval=INTERVAL):
    """One loop per IoT device (throughput + ping), both router sides, and TCP internals."""
    info(f'*** Starting network monitoring (every {interval}s)\n')
    shutil.rmtree(METRICS_DIR, ignore_errors=True)    # remove last run's logs
    os.makedirs(METRICS_DIR)

    dst = cloud.IP()                                  # 172.16.0.11
    for name, h in hosts.items():
        start_device_monitor(h, name, f'{name}-eth0', ping_dst=dst, interval=interval)
    start_device_monitor(router, 'router_lan', 'r-eth0', interval=interval)
    start_device_monitor(router, 'router_wan', 'r-eth1', interval=interval)

    shutil.rmtree(TCP_DIR, ignore_errors=True)        # remove last run's TCP logs
    os.makedirs(TCP_DIR)
    for name in TCP_HOSTS:
        start_tcp_monitor(hosts[name], name, dst, interval=interval)


def stop_network_monitoring():
    """Kill every monitoring loop we started (and only those)."""
    info('*** Stopping network monitoring\n')
    for node, pid in _monitor_pids:
        node.cmd(f'kill {pid} 2>/dev/null')
    _monitor_pids.clear()