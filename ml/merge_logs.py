"""Step 24 - merge the logs of one session into one table.

One output row = one device in one 2-second window, with everything
known about that moment: its own measurements, the shared link, its
TCP state, its sensor messages and the event that was running.

    python3 -m ml.merge_logs --session 1
    python3 -m ml.merge_logs --all
"""
import argparse
import bisect
import csv
import json
import os

RAW_DIR = 'data/raw'
OUT_DIR = 'data/merged'
MAX_GAP_S = 2.5          # a reading from another log must be this close in time

PROTECTED = ['camera', 'doorbell', 'lock', 'thermostat', 'speaker', 'light', 'plug']
LIMITABLE = ['phone', 'tv', 'laptop']
DEVICES = PROTECTED + LIMITABLE

NET_COLS = ['rx_kbps', 'tx_kbps', 'rtt_ms', 'jitter_ms', 'loss_pct']
TCP_COLS = ['conns', 'cwnd', 'ssthresh', 'srtt_ms', 'retrans_total', 'unacked']

OUT_COLS = (['session', 'seed', 't_s', 'timestamp', 'device', 'role'] + NET_COLS +
            ['lan_rx_kbps', 'lan_tx_kbps', 'wan_rx_kbps', 'wan_tx_kbps'] +
            ['tcp_' + c for c in TCP_COLS] +
            ['mqtt_msgs', 'mqtt_delay_ms'] +
            ['event_id', 'event_type', 'event_devices', 'involved', 'should_act'])


def num(text):
    """Text -> number, or '' when the field is empty or not a number."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return ''


def read_log(path, n_values):
    """Read 'timestamp,device,v1,v2,...' -> sorted list of (timestamp, [values])."""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            parts = line.strip().split(',')
            ts = num(parts[0])
            if ts == '' or len(parts) < 2:
                continue                              # header or broken line
            values = [num(p) for p in parts[2:2 + n_values]]
            values += [''] * (n_values - len(values))
            rows.append((ts, values))
    rows.sort(key=lambda r: r[0])
    return rows


def nearest(rows, times, ts, n_values):
    """Values of the row closest in time to ts, or blanks if none is close enough."""
    if not rows:
        return [''] * n_values
    i = bisect.bisect_left(times, ts)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(rows):
            if best is None or abs(rows[j][0] - ts) < abs(rows[best][0] - ts):
                best = j
    if abs(rows[best][0] - ts) > MAX_GAP_S:
        return [''] * n_values
    return rows[best][1]


def read_mqtt(path):
    """mqtt_received.log -> {device: sorted list of (arrival_time, delay_ms)}."""
    out = {d: [] for d in DEVICES}
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            parts = line.strip().split(',', 2)        # arrival, topic, payload
            if len(parts) < 3:
                continue
            arrival = num(parts[0])
            if arrival == '':
                continue
            device = next((d for d in DEVICES if d in parts[1]), None)
            sent = ''
            for field in parts[2].split(';'):
                if field.startswith('ts='):
                    sent = num(field[3:])
            if device is None or sent == '':
                continue
            if sent > 1e17:                           # nanoseconds
                sent /= 1e9
            elif sent > 1e11:                         # milliseconds
                sent /= 1e3
            out[device].append((arrival, (arrival - sent) * 1000.0))
    for d in out:
        out[d].sort()
    return out


def read_events(path):
    """events.csv -> list of events with real start, real end and devices."""
    events = {}
    if not os.path.exists(path):
        return []
    with open(path) as f:
        for row in csv.DictReader(f):
            ts = num(row.get('timestamp'))
            if ts == '':
                continue
            key = row.get('schedule_id') or row.get('event_id')
            ev = events.setdefault(key, {
                'id': key, 'type': row['event_type'], 'devices': [],
                'start': None, 'end': None,
                'should_act': 1 if str(row.get('should_act')).strip() == 'True' else 0})
            if row['device'] not in ev['devices']:
                ev['devices'].append(row['device'])
            if row['phase'] == 'start':
                ev['start'] = ts if ev['start'] is None else min(ev['start'], ts)
            elif row['phase'] == 'end':
                ev['end'] = ts if ev['end'] is None else max(ev['end'], ts)
    return [e for e in events.values() if e['start'] is not None and e['end'] is not None]


def event_at(events, ts):
    for ev in events:
        if ev['start'] <= ts <= ev['end']:
            return ev
    return None


def merge_session(session_dir):
    """Return the merged rows of one session folder."""
    with open(os.path.join(session_dir, 'meta.json')) as f:
        meta = json.load(f)
    net_dir = os.path.join(session_dir, 'network_metrics')
    tcp_dir = os.path.join(session_dir, 'tcp_metrics')

    lan = read_log(os.path.join(net_dir, 'router_lan.log'), 2)
    wan = read_log(os.path.join(net_dir, 'router_wan.log'), 2)
    lan_t = [r[0] for r in lan]
    wan_t = [r[0] for r in wan]
    mqtt = read_mqtt(os.path.join(session_dir, 'mqtt_received.log'))
    events = read_events(os.path.join(session_dir, 'events.csv'))

    per_device = {d: read_log(os.path.join(net_dir, d + '.log'), len(NET_COLS)) for d in DEVICES}
    starts = [rows[0][0] for rows in per_device.values() if rows]
    if not starts:
        return []
    t0 = min(starts)

    out = []
    for device in DEVICES:
        tcp = read_log(os.path.join(tcp_dir, device + '.log'), len(TCP_COLS))
        tcp_t = [r[0] for r in tcp]
        msgs = mqtt[device]
        prev_ts = None
        k = 0
        for ts, values in per_device[device]:
            window_start = prev_ts if prev_ts is not None else ts - meta.get('interval_s', 2)
            while k < len(msgs) and msgs[k][0] <= window_start:
                k += 1
            delays = []
            m = k
            while m < len(msgs) and msgs[m][0] <= ts:
                delays.append(msgs[m][1])
                m += 1
            k = m
            ev = event_at(events, ts)
            row = [meta['session'], meta['seed'], round(ts - t0, 1), ts, device,
                   'protected' if device in PROTECTED else 'limitable']
            row += values
            row += nearest(lan, lan_t, ts, 2) + nearest(wan, wan_t, ts, 2)
            row += nearest(tcp, tcp_t, ts, len(TCP_COLS))
            row += [len(delays), round(sum(delays) / len(delays), 1) if delays else '']
            if ev:
                row += [ev['id'], ev['type'], '|'.join(ev['devices']),
                        1 if device in ev['devices'] else 0, ev['should_act']]
            else:
                row += ['', 'normal', '', 0, 0]
            out.append(row)
            prev_ts = ts
    out.sort(key=lambda r: (r[3], r[4]))
    return out


def write_rows(path, rows):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(OUT_COLS)
        w.writerows(rows)


def summary(name, rows):
    counts = {}
    for r in rows:
        counts[r[OUT_COLS.index('event_type')]] = counts.get(r[OUT_COLS.index('event_type')], 0) + 1
    parts = ', '.join(f'{k} {v}' for k, v in sorted(counts.items()))
    print(f'{name}: {len(rows)} rows  ({parts})')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--session', type=int)
    p.add_argument('--all', action='store_true')
    args = p.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)

    if args.all:
        names = sorted(n for n in os.listdir(RAW_DIR) if n.startswith('session_'))
    elif args.session is not None:
        names = [f'session_{args.session:03d}']
    else:
        p.error('give --session N or --all')

    everything = []
    for name in names:
        rows = merge_session(os.path.join(RAW_DIR, name))
        write_rows(os.path.join(OUT_DIR, name + '.csv'), rows)
        summary(name, rows)
        everything += rows
    if args.all:
        write_rows(os.path.join(OUT_DIR, 'all_sessions.csv'), everything)
        print(f'all_sessions.csv: {len(everything)} rows from {len(names)} sessions')


if __name__ == '__main__':
    main()