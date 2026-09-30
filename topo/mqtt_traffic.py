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


def start_mqtt_device(h, name, interval, log_file=LOG_FILE):
    """One IoT sensor that publishes a reading forever, at random intervals."""
    lo, hi = interval
    topic = f'home/{name}/telemetry'
    cmd = (
        f'while true; do '
        f'VAL=$(( 18 + RANDOM % 8 )); '
        f'MSG="temp=$VAL"; '
        f'mosquitto_pub -h {BROKER_IP} -p {MQTT_PORT} -q 1 '
        f'-t {topic} -m "$MSG" > /dev/null 2>&1; '
        f'echo "$(date +%s.%N),{name},mqtt,${{#MSG}}B,burst" >> {log_file}; '
        f'sleep $(( {lo} + RANDOM % ({hi}-{lo}+1) )); '
        f'done &'
    )
    h.cmd(cmd)


def start_mqtt_traffic(hosts, cloud):
    """Fresh logs, broker on the cloud, then the sensors."""
    info('*** Starting MQTT traffic\n')
    cloud.cmd(f'rm -f {LOG_FILE} {MQTT_LOG}')          # fresh logs each run
    start_mqtt_broker(cloud)
    start_mqtt_device(hosts['thermostat'], 'thermostat', interval=(20, 40))


def stop_mqtt_traffic(hosts, cloud):
    """Stop every background job on the IoT devices and the cloud."""
    info('*** Stopping MQTT traffic\n')
    for h in list(hosts.values()) + [cloud]:
        h.cmd('kill $(jobs -p) 2>/dev/null')