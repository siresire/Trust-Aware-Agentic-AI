#!/usr/bin/env python3
"""
smart_home_topo.py - the smart-home IoT network for
"Trust-Aware Agentic AI for Smart-Home IoT Network Management".

Interactive:       sudo python3 topo/smart_home_topo.py [--seed 42] [--no-pcap]
From other folders: from topo.smart_home_topo import build_network, start_services, stop_services
"""

import argparse
import json
import os
import random
import time

from mininet.net import Mininet
from mininet.node import OVSSwitch, Node
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

from mqtt_traffic import start_mqtt_traffic, stop_mqtt_traffic
from normal_traffic import start_normal_traffic, stop_normal_traffic
from network_monitor import start_network_monitoring, stop_network_monitoring
from congestion import (reset_events_log, random_congestion,
                        floods_running, stop_all_floods)
from faults import random_fault, faults_running, stop_all_faults, reset_faults


# Project root = the folder above topo/, so paths work no matter where you run from
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE_DIR = os.path.join(PROJECT_ROOT, 'captures')

PORT_MAP_FILE = '/tmp/port_map.json'   # device -> s1 port, used later by the agent
DEFAULT_SEED = 42                      # override with --seed N

# (name, IP address/subnet) for every smart-home IoT device
DEVICES = [
    ('camera',     '10.0.0.1/24'),
    ('doorbell',   '10.0.0.2/24'),
    ('lock',       '10.0.0.3/24'),
    ('thermostat', '10.0.0.4/24'),
    ('speaker',    '10.0.0.5/24'),
    ('light',      '10.0.0.6/24'),
    ('plug',       '10.0.0.7/24'),
    ('phone',      '10.0.0.8/24'),
    ('tv',         '10.0.0.9/24'),
    ('laptop',     '10.0.0.10/24'),
]


class LinuxRouter(Node):
    """A host that forwards packets between its network cards."""

    def config(self, **params):
        super(LinuxRouter, self).config(**params)
        self.cmd('sysctl -w net.ipv4.ip_forward=1')    # turn forwarding ON

    def terminate(self):
        self.cmd('sysctl -w net.ipv4.ip_forward=0')    # turn it OFF when done
        super(LinuxRouter, self).terminate()


class SmartHomeCLI(CLI):
    """The normal mininet> prompt, plus our own commands."""

    def __init__(self, net, rng, **kwargs):
        self.rng = rng                       # must be set before CLI starts the prompt
        super().__init__(net, **kwargs)

    def _busy(self):
        """True (and a message) if a flood or fault is still running: no overlapping events."""
        if floods_running() or faults_running():
            print('An event is still running: wait for it to end, or type stopflood / stopfault')
            return True
        return False

    def do_congest(self, line):
        """congest [severe|border] -- start a random labelled congestion event"""
        kind = line.strip() or None
        if kind not in (None, 'severe', 'border'):
            print('usage: congest [severe|border]')
            return
        if self._busy():
            return
        ev = random_congestion(self.mn, self.rng, kind)
        print(f"event {ev['event_id']}: {ev['event_type']}, flooders {ev['flooders']}, "
              f"{ev['rate_mbps']} Mbit/s each, {ev['duration']} s")

    def do_stopflood(self, line):
        """stopflood -- end any running congestion event early"""
        stop_all_floods()

    def do_fault(self, line):
        """fault [wan|devlink] -- start a random labelled decoy fault"""
        kind = line.strip() or None
        if kind not in (None, 'wan', 'devlink'):
            print('usage: fault [wan|devlink]')
            return
        if self._busy():
            return
        ev = random_fault(self.mn, self.rng, kind)
        print(f"event {ev['event_id']}: {ev['event_type']} on {ev['target']}, "
              f"delay {ev['delay_ms']} ms, loss {ev['loss_pct']} %, {ev['duration']} s")

    def do_stopfault(self, line):
        """stopfault -- end any running fault early (the cable is restored)"""
        stop_all_faults()


def build_network():
    """Create (but do not start) the network. Returns (net, hosts, cloud, router)."""
    net = Mininet(switch=OVSSwitch, link=TCLink, controller=None)

    info('*** Adding the home switch and the WAN switch\n')
    s1 = net.addSwitch('s1', failMode='standalone')
    s2 = net.addSwitch('s2', failMode='standalone')  # ISP / WAN side

    info('*** Adding the router\n')
    router = net.addHost('router', cls=LinuxRouter, ip=None)

    info('*** Adding the smart-home IoT devices\n')
    hosts = {}
    for name, ip in DEVICES:
        hosts[name] = net.addHost(name, ip=ip, defaultRoute='via 10.0.0.254')

    info('*** Adding the cloud (internet) host\n')
    cloud = net.addHost('cloud', ip='172.16.0.11/24',
                        defaultRoute='via 172.16.0.1')

    info('*** Plugging every device into s1\n')
    for name in hosts:
        net.addLink(hosts[name], s1, bw=10, delay='5ms', loss=0)

    info('*** Plugging the router into s1\n')
    net.addLink(router, s1, bw=10, delay='5ms', loss=0,
                intfName1='r-eth0',
                params1={'ip': '10.0.0.254/24'})

    info('*** Connecting the router and the cloud to s2\n')
    net.addLink(router, s2, bw=10, delay='10ms', loss=0,
                intfName1='r-eth1',
                params1={'ip': '172.16.0.1/24'})
    net.addLink(s2, cloud, bw=10, delay='10ms', loss=0)

    return net, hosts, cloud, router


def write_port_map(net, hosts, path=PORT_MAP_FILE):
    """Record which s1 port each IoT device is plugged into, e.g. {'laptop': 's1-eth10'}."""
    s1 = net.get('s1')
    ports = {}
    for name, h in hosts.items():
        dev_intf, switch_intf = h.connectionsTo(s1)[0]
        ports[name] = switch_intf.name
    with open(path, 'w') as f:
        json.dump(ports, f, indent=2)
    info(f'*** Port map written to {path}\n')
    return ports


def start_capture(router):
    """Record every packet on both router sides into captures/<lan|wan>_<time>.pcap."""
    info('*** Starting packet capture\n')
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    stamp = time.strftime('%Y%m%d_%H%M%S')
    lan_file = f'{CAPTURE_DIR}/lan_{stamp}.pcap'
    wan_file = f'{CAPTURE_DIR}/wan_{stamp}.pcap'
    router.cmd(f'tcpdump -i r-eth0 -U -Z root -w {lan_file} '
               f'> {CAPTURE_DIR}/tcpdump_lan.log 2>&1 &')
    router.cmd(f'tcpdump -i r-eth1 -U -Z root -w {wan_file} '
               f'> {CAPTURE_DIR}/tcpdump_wan.log 2>&1 &')
    info(f'*** LAN capture: {lan_file}\n')
    info(f'*** WAN capture: {wan_file}\n')


def stop_capture(router):
    """Stop both tcpdumps cleanly (like Ctrl+C) so the files are complete."""
    info('*** Stopping packet capture\n')
    router.cmd('pkill -INT -f "tcpdump -i r-eth"')
    time.sleep(1)    # give tcpdump a moment to finish writing


def start_services(net, hosts, cloud, router, seed, pcap=True):
    """Everything that runs on top of the network, in the right order."""
    if pcap:
        start_capture(router)
    start_mqtt_traffic(hosts, cloud, seed)
    start_normal_traffic(hosts, cloud, seed)
    start_network_monitoring(hosts, router, cloud)
    reset_events_log()
    reset_faults()
    write_port_map(net, hosts)


def stop_services(hosts, cloud, router, pcap=True):
    """Reverse order: events, monitoring, traffic, then capture."""
    stop_all_floods()
    stop_all_faults()
    time.sleep(1)                          # let each event write its END line
    stop_network_monitoring()
    stop_normal_traffic(hosts, cloud)
    stop_mqtt_traffic(hosts, cloud)
    if pcap:
        stop_capture(router)


def run(seed=DEFAULT_SEED, pcap=True):
    """Interactive mode: build, start, mininet> prompt, always clean up."""
    net, hosts, cloud, router = build_network()

    info('*** Starting network\n')
    net.start()
    start_services(net, hosts, cloud, router, seed, pcap)

    try:
        SmartHomeCLI(net, rng=random.Random(seed))
    finally:
        stop_services(hosts, cloud, router, pcap)
        info('*** Stopping network\n')
        net.stop()


def parse_args():
    ap = argparse.ArgumentParser(description='Smart-home IoT network (interactive)')
    ap.add_argument('--seed', type=int, default=DEFAULT_SEED,
                    help='seed for traffic and event choices (default 42)')
    ap.add_argument('--no-pcap', action='store_true',
                    help='do not record packet captures')
    return ap.parse_args()


if __name__ == '__main__':
    args = parse_args()
    setLogLevel('info')
    run(seed=args.seed, pcap=not args.no_pcap)