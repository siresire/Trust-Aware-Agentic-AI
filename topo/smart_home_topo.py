import os
import time

from mininet.net import Mininet
from mininet.node import OVSSwitch, Node
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

from mqtt_traffic import start_mqtt_traffic, stop_mqtt_traffic
from normal_traffic import start_normal_traffic, stop_normal_traffic
from network_monitor import start_network_monitoring, stop_network_monitoring


# Project root = the folder above topo/, so paths work no matter where you run from
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE_DIR = os.path.join(PROJECT_ROOT, 'captures')

SEED = 42    # change this to generate a different (but repeatable) run


class LinuxRouter(Node):
    """A host that forwards packets between its network cards."""

    def config(self, **params):
        super(LinuxRouter, self).config(**params)
        self.cmd('sysctl -w net.ipv4.ip_forward=1')    # turn forwarding ON

    def terminate(self):
        self.cmd('sysctl -w net.ipv4.ip_forward=0')    # turn it OFF when done
        super(LinuxRouter, self).terminate()


def run():
    net = Mininet(switch=OVSSwitch, link=TCLink, controller=None)

    info('*** Adding the home switch\n')
    s1 = net.addSwitch('s1', failMode='standalone')
    s2 = net.addSwitch('s2', failMode='standalone')  # ISP / WAN side

    info('*** Adding the router\n')
    router = net.addHost('router', cls=LinuxRouter, ip=None)

    devices = [
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

    info('*** Adding the smart-home IoT devices\n')
    hosts = {}
    for name, ip in devices:
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

    info('*** Starting network\n')
    net.start()

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

    start_mqtt_traffic(hosts, cloud, SEED)
    start_normal_traffic(hosts, cloud, SEED)
    start_network_monitoring(hosts, router, cloud)

    CLI(net)

    stop_network_monitoring()
    stop_normal_traffic(hosts, cloud)
    stop_mqtt_traffic(hosts, cloud)

    info('*** Stopping packet capture\n')
    router.cmd('pkill -INT -f "tcpdump -i r-eth"')
    time.sleep(1)    # give tcpdump a moment to finish writing

    info('*** Stopping network\n')
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run()