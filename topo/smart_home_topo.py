from mininet.net import Mininet
from mininet.node import OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info


def run():
    net = Mininet(switch=OVSSwitch, controller=None)

    info('*** Adding the home switch\n')
    s1 = net.addSwitch('s1', failMode='standalone')

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
        hosts[name] = net.addHost(name, ip=ip)

    info('*** Plugging every device into s1\n')
    for name in hosts:
        net.addLink(hosts[name], s1)

    info('*** Starting network\n')
    net.start()
    CLI(net)
    info('*** Stopping network\n')
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run()