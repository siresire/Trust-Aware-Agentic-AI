"""
sources.py - where the page's numbers come from.
  Live    the running Mininet testbed (/tmp logs) and the running agent's log
  Replay  one recorded session of the experiment (data/raw + data/experiment2), seen as it was
          at a chosen moment `at`. Every answer is cut off at `at`, so a replay looks exactly
          like the live page did at that time.
Both have the same methods, so api.py does not care which one it gets.
"""
import bisect
import glob
import json
import os
import re
import threading
import time

from dashboards.web import config, logs


class Live:
    kind = 'live'

    def __init__(self, agent_path):
        self.agent_path = agent_path

    def now(self):
        return time.time()

    def metrics(self, name, n):
        return logs.history(logs.metric_file(name), logs.parse_metric, n)

    def tcp(self, name, n):
        return logs.history(logs.tcp_file(name), logs.parse_tcp, n)

    def agent(self, n=2000):
        return logs.agent_log(self.agent_path, n)

    def events(self):
        return logs.events(logs.read(config.EVENTS_LOG, 2000))

    def protocols(self):
        return logs.protocols()

    def info(self):
        return {'kind': 'live', 'agent_log': self.agent_path}


class Session:
    """One recorded session, read once and kept in memory."""

    def __init__(self, sid):
        self.sid = sid
        raw = os.path.join(config.RAW_DIR, f'session_{sid}')
        self.meta = json.load(open(os.path.join(raw, 'meta.json')))
        self.rows, self.times = {}, {}
        for name in config.DEVICES + ['router_wan', 'router_lan']:
            rows = logs.history(os.path.join(raw, 'network_metrics', name + '.log'), logs.parse_metric, 10 ** 6)
            self.rows[name], self.times[name] = rows, [r['timestamp'] for r in rows]
        self.tcp_rows = {}
        for name in config.LIMITABLE:
            rows = logs.history(os.path.join(raw, 'tcp_metrics', name + '.log'), logs.parse_tcp, 10 ** 6)
            self.tcp_rows[name] = (rows, [r['timestamp'] for r in rows])
        self.all_events = logs.events(logs.read(os.path.join(raw, 'events.csv'), 10 ** 5))
        found = glob.glob(os.path.join(config.EXP_DIR, f'agent_{sid}_*.jsonl'))
        self.agent_path = found[0] if found else None
        self.start, self.ticks, self.actions = logs.agent_log(self.agent_path, 10 ** 6) if found else ({}, [], [])
        self.tick_t = [t['t'] for t in self.ticks]
        cam = self.times[config.WATCH]
        self.t0 = cam[0] if cam else (self.tick_t[0] if self.tick_t else 0)
        self.t1 = cam[-1] if cam else (self.tick_t[-1] if self.tick_t else 0)
        self.mode = self.start.get('mode', '?')
        self.mtime = os.path.getmtime(os.path.join(raw, 'meta.json'))


_cache = {}
_lock = threading.Lock()


def session(sid):
    """A recorded session, read once (the 9 runs of the experiment take about 20 MB of memory)."""
    with _lock:                                   # many requests arrive at once: read each file only once
        s = _cache.get(sid)
        if s is None or s.mtime != os.path.getmtime(os.path.join(config.RAW_DIR, f'session_{sid}', 'meta.json')):
            if len(_cache) >= 30:
                _cache.clear()
            s = _cache[sid] = Session(sid)
        return s


class Replay:
    kind = 'replay'

    def __init__(self, sid, at=None):
        self.s = session(sid)
        self.at = min(self.s.t1, max(self.s.t0, at if at is not None else self.s.t0 + 120))

    def now(self):
        return self.at

    def _cut(self, rows, times, n):
        i = bisect.bisect_right(times, self.at)
        return rows[max(0, i - n):i]

    def metrics(self, name, n):
        return self._cut(self.s.rows.get(name, []), self.s.times.get(name, []), n)

    def tcp(self, name, n):
        rows, times = self.s.tcp_rows.get(name, ([], []))
        return self._cut(rows, times, n)

    def agent(self, n=2000):
        ticks = self._cut(self.s.ticks, self.s.tick_t, n)
        actions = [a for a in self.s.actions if a['t'] <= self.at]
        return self.s.start, ticks, actions

    def events(self):
        out = []
        for e in self.s.all_events:
            if e['start'] <= self.at:
                out.append({**e, 'end': e['end'] if e['end'] and e['end'] <= self.at else None})
        return out

    def protocols(self):
        return {}

    def info(self):
        m = self.s.meta
        return {'kind': 'replay', 'session': self.s.sid, 'seed': m.get('seed'), 'mode': self.s.mode,
                'recorded': m.get('start'), 't0': self.s.t0, 't1': self.s.t1, 'at': self.at,
                'elapsed': round(self.at - self.s.t0, 1), 'length': round(self.s.t1 - self.s.t0, 1),
                'events': [{'type': e['type'], 'devices': e['devices'], 'start': e['start'], 'end': e['end']}
                           for e in self.s.all_events]}


def list_sessions():
    """Every recorded session that has both its network logs and an agent log."""
    out = []
    for path in sorted(glob.glob(os.path.join(config.EXP_DIR, 'agent_*_*.jsonl'))):
        m = re.match(r'agent_(\d+)_(\w+)\.jsonl$', os.path.basename(path))
        meta_path = os.path.join(config.RAW_DIR, f'session_{m.group(1)}', 'meta.json') if m else ''
        if not m or not os.path.exists(meta_path):
            continue
        meta = json.load(open(meta_path))
        out.append({'session': int(m.group(1)), 'mode': m.group(2), 'seed': meta.get('seed'),
                    'recorded': meta.get('start'), 'events': meta.get('n_events'),
                    'length_s': meta.get('duration_actual_s')})
    return sorted(out, key=lambda s: (s['seed'] or 0, config.MODES.index(s['mode']) if s['mode'] in config.MODES else 9))


def get(q, agent_path):
    """The source a request asks for: ?src=replay&session=421&at=1792683300 (default: live)."""
    if q.get('src', ['live'])[0] == 'replay':
        sid = int(q.get('session', ['0'])[0])
        at = q.get('at', [None])[0]
        return Replay(sid, float(at) if at else None)
    return Live(agent_path)
