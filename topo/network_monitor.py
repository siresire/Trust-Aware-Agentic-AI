"""
network_monitor.py - measures every IoT device and the router while the network runs.
Step 11: throughput from byte counters. Used by smart_home_topo.py.
"""

import os
import shutil

from mininet.log import info

METRICS_DIR = '/tmp/network_metrics'   # one log file per device / router side
INTERVAL = 2                           # seconds between measurements

_monitor_pids = []                     # (node, pid) of every loop we start, to stop exactly those


def start_throughput_monitor(node, label, iface, interval=INTERVAL,
                             metrics_dir=METRICS_DIR):
    """Every `interval` s, log how many kbit/s went in and out of one network card."""
    log = f'{metrics_dir}/{label}.log'
    with open(log, 'w') as f:
        f.write('timestamp,device,rx_kbps,tx_kbps\n')

    stats = f'/sys/class/net/{iface}/statistics'
    cmd = (
        f'( while true; do '
        f'RX1=$(cat {stats}/rx_bytes); TX1=$(cat {stats}/tx_bytes); '
        f'sleep {interval}; '
        f'RX2=$(cat {stats}/rx_bytes); TX2=$(cat {stats}/tx_bytes); '
        f'RX_KBPS=$(( (RX2-RX1)*8/1000/{interval} )); '
        f'TX_KBPS=$(( (TX2-TX1)*8/1000/{interval} )); '
        f'echo "$(date +%s.%N),{label},$RX_KBPS,$TX_KBPS" >> {log}; '
        f'done ) &'
    )
    node.cmd(cmd)
    pid = node.cmd('echo $!').strip()
    _monitor_pids.append((node, pid))


def start_network_monitoring(hosts, router, interval=INTERVAL):
    """One throughput loop per IoT device, plus both sides of the router."""
    info(f'*** Starting network monitoring (every {interval}s)\n')
    shutil.rmtree(METRICS_DIR, ignore_errors=True)    # remove last run's logs
    os.makedirs(METRICS_DIR)

    for name, h in hosts.items():
        start_throughput_monitor(h, name, f'{name}-eth0', interval)
    start_throughput_monitor(router, 'router_lan', 'r-eth0', interval)
    start_throughput_monitor(router, 'router_wan', 'r-eth1', interval)


def stop_network_monitoring():
    """Kill every monitoring loop we started (and only those)."""
    info('*** Stopping network monitoring\n')
    for node, pid in _monitor_pids:
        node.cmd(f'kill {pid} 2>/dev/null')
    _monitor_pids.clear()