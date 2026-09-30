"""
mqtt_traffic.py - MQTT broker on the cloud and IoT sensors publishing to it.
Used by smart_home_topo.py.
"""

from mininet.log import info

LOG_FILE  = '/tmp/normal_traffic.log'     # every traffic event a device SENT
MQTT_LOG  = '/tmp/mqtt_received.log'      # every message the broker DELIVERED
MOSQ_CONF = '/tmp/mosquitto_cloud.conf'   # broker settings file
BROKER_IP = '172.16.0.11'                 # the cloud host
MQTT_PORT = 1883                          # standard MQTT port

# One profile per MQTT sensor: how often it publishes, how reliably, and what it says
MQTT_PROFILES = {
    'thermostat': dict(interval=(20, 40),   qos=0,
                       payload='temp=$(( 18 + RANDOM % 8 ))'),
    'lock':       dict(interval=(120, 300), qos=1,
                       payload='state=locked;battery=$(( 60 + RANDOM % 41 ))'),
    'doorbell':   dict(interval=(60, 180),  qos=1,
                       payload='event=motion'),
    'light':      dict(interval=(300, 600), qos=0,
                       payload='on=$(( RANDOM % 2 ));brightness=$(( RANDOM % 101 ))'),
    'plug':       dict(interval=(300, 600), qos=0,
                       payload='on=1;power_w=$(( RANDOM % 1500 ))'),
}


def device_seed(seed, name):
    """A different but repeatable seed for each device."""
    return seed * 1000 + sum(ord(c) for c in name)


def start_mqtt_broker(cloud):
    """Start Mosquitto on the cloud and a subscriber that records every message."""
    info('*** Starting MQTT broker on cloud\n')
    with open(MOSQ_CONF, 'w') as f:
        f.write(f'listener {MQTT_PORT} 0.0.0.0\n')
        f.write('allow_anonymous true\n')

    cloud.cmd(f'mosquitto -c {MOSQ_CONF} > /tmp/mosquitto.log 2>&1 &')
    cloud.cmd('sleep 1')
    cloud.cmd(f'mosquitto_sub -h 127.0.0.1 -p {MQTT_PORT} -t "home/#" '
              f'-F "%U,%t,%p" > {MQTT_LOG} 2>&1 &')


def start_mqtt_device(h, name, profile, seed, log_file=LOG_FILE):
    """One IoT sensor that publishes forever, following its profile."""
    lo, hi = profile['interval']
    qos = profile['qos']
    payload = profile['payload']
    topic = f'home/{name}/telemetry'
    cmd = (
        f'( RANDOM={seed}; sleep $(( RANDOM % 5 )); '
        f'while true; do '
        f'MSG="{payload}"; '
        f'mosquitto_pub -h {BROKER_IP} -p {MQTT_PORT} -q {qos} '
        f'-t {topic} -m "$MSG" > /dev/null 2>&1; '
        f'echo "$(date +%s.%N),{name},mqtt,${{#MSG}}B,burst" >> {log_file}; '
        f'sleep $(( {lo} + RANDOM % ({hi}-{lo}+1) )); '
        f'done ) &'
    )
    h.cmd(cmd)


def start_mqtt_traffic(hosts, cloud, seed):
    """Fresh logs, broker on the cloud, then the sensors (each with its own seed)."""
    info(f'*** Starting MQTT traffic (seed={seed})\n')
    cloud.cmd(f'rm -f {LOG_FILE} {MQTT_LOG}')          # fresh logs each run
    start_mqtt_broker(cloud)
    for name, profile in MQTT_PROFILES.items():
        start_mqtt_device(hosts[name], name, profile, device_seed(seed, name))


def stop_mqtt_traffic(hosts, cloud):
    """Stop every background job on the IoT devices and the cloud."""
    info('*** Stopping MQTT traffic\n')
    for h in list(hosts.values()) + [cloud]:
        h.cmd('kill $(jobs -p) 2>/dev/null')