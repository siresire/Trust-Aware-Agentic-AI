"""
congestion.py - labelled congestion events from devices the agent may limit.
Every flooder writes a START and an END line (with real times) to EVENT_LOG.
Used by smart_home_topo.py.
"""

import glob
import os
import signal
import time

from mininet.log import info

from mqtt_traffic import BROKER_IP as CLOUD_IP
from normal_traffic import IPERF_PORT

EVENT_LOG = '/tmp/events.log'      # ground truth: start/end of every event
FLOOD_DIR = '/tmp/floods'          # one small file per running flood, holding its PID

ALLOWED_FLOODERS = ['laptop', 'phone', 'tv']   # never camera, lock, doorbell, sensors...


def reset_events_log():
    """Start each run with an empty events log (header only) and no leftover PID files."""
    os.makedirs(FLOOD_DIR, exist_ok=True)
    for pidfile in glob.glob(f'{FLOOD_DIR}/*.pid'):
        os.remove(pidfile)
    with open(EVENT_LOG, 'w') as f:
        f.write('timestamp,event_id,event_type,device,params,duration_s,phase\n')


def start_congestion_event(net, flooders, rate_mbps, duration, event_type):
    """Make each flooder upload at rate_mbps for `duration` s. Returns the event id."""
    for name in flooders:
        if name not in ALLOWED_FLOODERS:
            raise ValueError(f'{name} is protected and may not flood')

    event_id = int(time.time() * 1000)            # milliseconds: unique per event
    info(f'*** Congestion event {event_id} ({event_type}): {flooders} '
         f'at {rate_mbps} Mbit/s each for {duration}s\n')

    for name in flooders:
        host = net.get(name)
        pidfile = f'{FLOOD_DIR}/{event_id}_{name}.pid'
        fields = (f'{event_id},{event_type},{name},'
                  f'proto=tcp;rate_mbps={rate_mbps},{duration}')
        cmd = (
            f'( echo "$(date +%s.%N),{fields},start" >> {EVENT_LOG}; '
            f'iperf -c {CLOUD_IP} -p {IPERF_PORT} -t {duration} -b {rate_mbps}M '
            f'> /dev/null 2>&1 & '
            f'echo $! > {pidfile}; '
            f'wait $!; '
            f'echo "$(date +%s.%N),{fields},end" >> {EVENT_LOG}; '
            f'rm -f {pidfile} ) &'
        )
        host.cmd(cmd)
    return event_id


def random_congestion(net, rng, kind=None):
    """Pick flooders, rate and duration at random (repeatable with a seeded rng)."""
    if kind is None:
        kind = 'severe' if rng.random() < 0.6 else 'border'

    if kind == 'severe':                           # 2-3 flooders, total > 15 Mbit/s
        flooders = rng.sample(ALLOWED_FLOODERS, rng.randint(2, 3))
        rate = rng.randint(8, 20)
        event_type = 'C_SEVERE'
    else:                                          # 1 flooder, sometimes enough to overload
        flooders = [rng.choice(ALLOWED_FLOODERS)]
        rate = rng.randint(6, 12)
        event_type = 'C_BORDER'

    duration = rng.randint(15, 60)
    event_id = start_congestion_event(net, flooders, rate, duration, event_type)
    return dict(event_id=event_id, event_type=event_type, flooders=flooders,
                rate_mbps=rate, duration=duration)


def floods_running():
    """True if any flood from any event is still running."""
    return bool(glob.glob(f'{FLOOD_DIR}/*.pid'))


def stop_all_floods():
    """End every running flood now; each one still writes its END line."""
    stopped = 0
    for pidfile in glob.glob(f'{FLOOD_DIR}/*.pid'):
        try:
            with open(pidfile) as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            stopped += 1
        except (ValueError, ProcessLookupError, FileNotFoundError):
            pass                                   # flood ended a moment ago
    info(f'*** Stopped {stopped} flood(s)\n')