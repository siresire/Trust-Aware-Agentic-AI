"""
logs.py - reads the log files. Read-only: it never changes a file.
"""
import json
import os
from collections import deque

from dashboards.web import config


def sf(v, d=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def si(v, d=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return d


def read(path, n=5000):
    """The last n lines of a file ([] if it does not exist yet)."""
    try:
        with open(path, 'r', errors='replace') as f:
            return list(deque(f, maxlen=n))
    except OSError:
        return []


def parse_metric(line):
    # timestamp,device,rx_kbps,tx_kbps,rtt_ms,jitter_ms,loss_pct
    p = line.strip().split(',')
    if len(p) != 7 or p[0] == 'timestamp' or sf(p[0]) is None:
        return None
    return {'timestamp': sf(p[0]), 'rx_kbps': sf(p[2], 0) or 0, 'tx_kbps': sf(p[3], 0) or 0,
            'rtt_ms': sf(p[4]), 'jitter_ms': sf(p[5]), 'loss_pct': sf(p[6])}


def parse_tcp(line):
    # timestamp,device,connections,cwnd,ssthresh,srtt_ms,retrans_total,unacked
    p = line.strip().split(',')
    if len(p) != 8 or p[0] == 'timestamp' or sf(p[0]) is None:
        return None
    return {'timestamp': sf(p[0]), 'connections': si(p[2], 0) or 0, 'cwnd': si(p[3]), 'ssthresh': si(p[4]),
            'srtt_ms': sf(p[5]), 'retrans_total': si(p[6], 0) or 0, 'unacked': si(p[7], 0) or 0}


def history(path, parser, n):
    return [r for r in (parser(l) for l in read(path, n)) if r]


def metric_file(name):
    return os.path.join(config.METRICS_DIR, name + '.log')


def tcp_file(name):
    return os.path.join(config.TCP_DIR, name + '.log')


def protocols():
    """Protocol per device from normal_traffic.log. If a device is not in that log,
    fall back to: has a TCP metrics file -> TCP, otherwise UDP."""
    proto = {}
    for line in read(config.TRAFFIC_LOG, 3000):
        p = line.strip().split(',')
        if len(p) >= 5 and p[2].strip():
            proto[p[1].strip()] = p[2].strip().lower()
    for d in config.DEVICES:
        if d not in proto:
            proto[d] = 'tcp' if os.path.exists(tcp_file(d)) else ('udp' if os.path.exists(metric_file(d)) else None)
    return proto


def recent_traffic(n=25):
    out = []
    for line in read(config.TRAFFIC_LOG, 200):
        p = line.strip().split(',')
        if len(p) >= 5 and sf(p[0]) is not None:
            out.append({'timestamp': sf(p[0]), 'device': p[1], 'protocol': p[2], 'size': p[3], 'kind': p[4]})
    return sorted(out, key=lambda e: e['timestamp'], reverse=True)[:n]


def uplink():
    """What leaves the house right now: the router's internet side (the same number the agent uses)."""
    rows = history(metric_file('router_wan'), parse_metric, 3)
    return rows[-1] if rows else None


def agent_log(path, n=2000):
    """The agent's log -> (start line, ticks, actions). Empty if the agent has not run yet."""
    start, ticks, actions = {}, [], []
    try:
        with open(path, errors='replace') as f:
            first = json.loads(f.readline() or '{}')         # the START line is always the first one
        if first.get('event') == 'START':
            start = first
    except (OSError, json.JSONDecodeError):
        pass
    for line in read(path, n):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue                                     # a line that is still being written
        if r.get('event') == 'START':
            start = r
        elif r.get('event') == 'TICK':
            ticks.append(r)
        elif r.get('event'):
            actions.append(r)
    return start, ticks, actions


def events(lines):
    """events.log / events.csv lines -> one dict per event, oldest first.
    end is None while the event is still running."""
    evs, cols = {}, None
    for line in lines:
        p = line.strip().split(',')
        if not p or not p[0]:
            continue
        if p[0] == 'timestamp':
            cols = p
            continue
        r = dict(zip(cols or ['timestamp', 'event_id', 'event_type', 'device', 'params', 'duration_s', 'phase'], p))
        t = sf(r.get('timestamp'))
        if t is None:
            continue
        key = r.get('schedule_id') or r.get('event_id')
        ev = evs.setdefault(key, {'id': key, 'type': r.get('event_type'), 'devices': [], 'params': r.get('params', ''),
                                  'start': None, 'end': None, 'planned_s': sf(r.get('duration_s')), 'n': 0})
        if r.get('device') and r['device'] not in ev['devices']:
            ev['devices'].append(r['device'])
        if r.get('phase') == 'start':
            ev['n'] += 1
            ev['start'] = t if ev['start'] is None else min(ev['start'], t)
        elif r.get('phase') == 'end':
            ev['n'] -= 1
            ev['end'] = t if ev['end'] is None else max(ev['end'], t)
    out = []
    for e in evs.values():
        if e['start']:
            if e.pop('n') > 0:
                e['end'] = None                 # one flooder still running
            out.append(e)
    return sorted(out, key=lambda e: e['start'])
