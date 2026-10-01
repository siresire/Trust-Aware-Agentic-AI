"""
faults.py - decoy faults that rate-limiting cannot fix.
F_WAN: the internet link gets slow/lossy. F_DEVLINK: one IoT device's own link gets lossy.
Each fault writes START and END lines to the same events log as congestion.
Used by smart_home_topo.py.
"""

import glob
import os
import signal
import time

from mininet.log import info

from congestion import EVENT_LOG

FAULT_DIR = '/tmp/faults'                  # one small file per running fault, holding its PID

WAN_BASE_DELAY_MS = 10                     # must match the WAN links in smart_home_topo.py
LAN_BASE_DELAY_MS = 5                      # must match the device links in smart_home_topo.py

FAULT_DEVICES = ['camera', 'doorbell', 'lock', 'thermostat', 'speaker']   # IoT devices whose link may fail


def find_netem(node, dev):
    """Return (location, handle) of the netem qdisc TCLink put on `dev`, e.g. ('parent 5:1', '10:')."""
    out = node.cmd(f'tc qdisc show dev {dev}')
    for line in out.splitlines():
        parts = line.split()
        if len(parts) > 2 and parts[1] == 'netem':
            handle = parts[2]
            if 'root' in parts:
                return 'root', handle
            return f"parent {parts[parts.index('parent') + 1]}", handle
    raise RuntimeError(f'no netem qdisc found on {dev}')


def _start_fault(node, dev, base_delay_ms, delay_ms, loss_pct, duration,
                 event_type, target):
    """Change dev's netem for `duration` s, then restore it. Logs START and END."""
    loc, handle = find_netem(node, dev)
    event_id = int(time.time() * 1000)
    pidfile = f'{FAULT_DIR}/{event_id}_{target}.pid'
    fields = (f'{event_id},{event_type},{target},'
              f'delay_ms={delay_ms};loss_pct={loss_pct},{duration}')
    apply = (f'tc qdisc change dev {dev} {loc} handle {handle} '
             f'netem delay {delay_ms}ms loss {loss_pct}%')
    restore = (f'tc qdisc change dev {dev} {loc} handle {handle} '
               f'netem delay {base_delay_ms}ms loss 0%')
    info(f'*** Fault {event_id} ({event_type}) on {target}: '
         f'delay {delay_ms} ms, loss {loss_pct} % for {duration}s\n')
    cmd = (
        f'( {apply}; '
        f'echo "$(date +%s.%N),{fields},start" >> {EVENT_LOG}; '
        f'sleep {duration} & '
        f'echo $! > {pidfile}; '
        f'wait $!; '
        f'{restore}; '
        f'echo "$(date +%s.%N),{fields},end" >> {EVENT_LOG}; '
        f'rm -f {pidfile} ) &'
    )
    node.cmd(cmd)
    return event_id


def wan_fault(net, delay_ms, loss_pct, duration):
    """F_WAN: the router's internet-side link gets slower and lossy."""
    router = net.get('router')
    return _start_fault(router, 'r-eth1', WAN_BASE_DELAY_MS, delay_ms, loss_pct,
                        duration, 'F_WAN', 'wan')


def device_link_fault(net, name, loss_pct, duration):
    """F_DEVLINK: one IoT device's own link gets lossy (delay unchanged)."""
    if name not in FAULT_DEVICES:
        raise ValueError(f'{name} is not in FAULT_DEVICES')
    node = net.get(name)
    return _start_fault(node, f'{name}-eth0', LAN_BASE_DELAY_MS, LAN_BASE_DELAY_MS,
                        loss_pct, duration, 'F_DEVLINK', name)


def random_fault(net, rng, kind=None):
    """Pick a fault type and its parameters at random (repeatable with a seeded rng)."""
    if kind is None:
        kind = 'wan' if rng.random() < 0.5 else 'devlink'
    duration = rng.randint(15, 60)

    if kind == 'wan':
        delay_ms = rng.randint(30, 80)             # normal WAN cable: 10 ms
        loss_pct = rng.randint(1, 5)
        event_id = wan_fault(net, delay_ms, loss_pct, duration)
        return dict(event_id=event_id, event_type='F_WAN', target='wan',
                    delay_ms=delay_ms, loss_pct=loss_pct, duration=duration)

    name = rng.choice(FAULT_DEVICES)
    loss_pct = rng.randint(5, 20)
    event_id = device_link_fault(net, name, loss_pct, duration)
    return dict(event_id=event_id, event_type='F_DEVLINK', target=name,
                delay_ms=LAN_BASE_DELAY_MS, loss_pct=loss_pct, duration=duration)


def faults_running():
    """True if any fault is still active."""
    return bool(glob.glob(f'{FAULT_DIR}/*.pid'))


def stop_all_faults():
    """End every active fault now; each one restores its cable and writes its END line."""
    os.makedirs(FAULT_DIR, exist_ok=True)
    stopped = 0
    for pidfile in glob.glob(f'{FAULT_DIR}/*.pid'):
        try:
            with open(pidfile) as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            stopped += 1
        except (ValueError, ProcessLookupError, FileNotFoundError):
            pass                                   # fault ended a moment ago
    info(f'*** Stopped {stopped} fault(s)\n')


def reset_faults():
    """Start each run with no leftover fault PID files."""
    os.makedirs(FAULT_DIR, exist_ok=True)
    for pidfile in glob.glob(f'{FAULT_DIR}/*.pid'):
        os.remove(pidfile)