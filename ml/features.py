""" python3 -m ml.features --session 1
    python3 -m ml.features --all
"""
import argparse
import bisect
import csv
import json
import os

IN_DIR = 'data/labelled'
OUT_DIR = 'data/features'

CAPACITY_KBPS = 10000.0  # the shared link (10 Mbit/s)
HISTORY = 3              # rows of history per device (about 6 seconds)
RATIO_CAP = 10.0         # rtt_ratio is cut off here; also used when there is no reply
STALE_S = 3.0            # another device's reading older than this is ignored
MQTT_WINDOW_S = 10.0     # sensor messages are summarised over this long

LIMITABLE = ['phone', 'tv', 'laptop']

META = ['session', 'seed', 't_s', 'timestamp', 'device', 'role',
        'event_id', 'event_type', 'event_devices', 'involved', 'should_act',
        'degraded', 'will_degrade', 'onset', 'label_valid']

BASIC = ['is_protected', 'tx_kbps', 'rx_kbps', 'rtt_ratio', 'jitter_ms', 'loss_pct', 'no_reply',
         'rtt_ratio_prev', 'rtt_ratio_mean', 'rtt_ratio_max', 'rtt_ratio_slope',
         'loss_mean', 'bad_count',
         'uplink_util', 'uplink_util_mean', 'uplink_util_slope',
         'n_bad_others', 'n_bad_protected', 'top_tx_kbps', 'top_tx_share',
         'limitable_tx_kbps', 'is_top_sender']

CROSS = ['home_tcp_srtt_max', 'home_tcp_retrans', 'home_tcp_cwnd_min', 'home_tcp_unacked',
         'home_mqtt_msgs', 'home_mqtt_delay_ms']

FEATURES = BASIC + CROSS


def f(text):
    """Text -> float, or None when empty."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def out(value, digits=3):
    return '' if value is None else round(value, digits)


def prepare(rows):
    """Numbers we need again and again, worked out once per row."""
    for r in rows:
        r['_t'] = float(r['timestamp'])
        rtt = f(r['rtt_ms'])
        thr = float(r['rtt_thr_ms'])
        r['_no_reply'] = 1 if rtt is None else 0
        r['_ratio'] = RATIO_CAP if rtt is None else min(rtt / thr, RATIO_CAP)
        loss = f(r['loss_pct'])
        r['_loss'] = 100.0 if (rtt is None and loss is None) else (loss or 0.0)
        r['_bad'] = int(r['bad'])
        r['_tx'] = f(r['tx_kbps']) or 0.0
        wan = f(r['wan_tx_kbps'])
        r['_util'] = None if wan is None else wan / CAPACITY_KBPS


def latest(dev_rows, dev_times, t):
    """The newest row of a device at or before time t, if it is fresh enough."""
    i = bisect.bisect_right(dev_times, t) - 1
    if i < 0 or t - dev_times[i] > STALE_S:
        return None
    return dev_rows[i]


def build_session(path):
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return []
    prepare(rows)

    by_device = {}
    for r in rows:
        by_device.setdefault(r['device'], []).append(r)
    times = {}
    for d, dev_rows in by_device.items():
        dev_rows.sort(key=lambda r: r['_t'])
        times[d] = [r['_t'] for r in dev_rows]

    # TCP retransmissions since the previous row, per limitable device
    for d in LIMITABLE:
        prev = None
        for r in by_device.get(d, []):
            cur = f(r['tcp_retrans_total'])
            r['_retr'] = max(0.0, cur - prev) if (cur is not None and prev is not None) else 0.0
            if cur is not None:
                prev = cur

    # every sensor message of the session: (arrival window time, count, delay)
    msgs = sorted((r['_t'], int(float(r['mqtt_msgs'])), f(r['mqtt_delay_ms']))
                  for r in rows if r['mqtt_msgs'] not in ('', '0', '0.0') and f(r['mqtt_delay_ms']) is not None)
    msg_times = [m[0] for m in msgs]

    result = []
    for d, dev_rows in by_device.items():
        for i, r in enumerate(dev_rows):
            t = r['_t']
            hist = dev_rows[max(0, i - HISTORY + 1):i + 1]          # current row and the ones before it
            before = dev_rows[max(0, i - HISTORY + 1):i]            # only the ones before it
            ratios = [x['_ratio'] for x in hist]
            utils = [x['_util'] for x in hist]

            feat = {
                'is_protected': 1 if r['role'] == 'protected' else 0,
                'tx_kbps': r['_tx'],
                'rx_kbps': f(r['rx_kbps']),
                'rtt_ratio': r['_ratio'],
                'jitter_ms': f(r['jitter_ms']),
                'loss_pct': r['_loss'],
                'no_reply': r['_no_reply'],
                'rtt_ratio_prev': before[-1]['_ratio'] if before else None,
                'rtt_ratio_mean': mean(ratios),
                'rtt_ratio_max': max(ratios),
                'rtt_ratio_slope': (r['_ratio'] - mean([x['_ratio'] for x in before])) if before else None,
                'loss_mean': mean([x['_loss'] for x in hist]),
                'bad_count': sum(x['_bad'] for x in hist),
                'uplink_util': r['_util'],
                'uplink_util_mean': mean(utils),
                'uplink_util_slope': (r['_util'] - mean([x['_util'] for x in before]))
                                     if (before and r['_util'] is not None and mean([x['_util'] for x in before]) is not None) else None,
            }

            # the rest of the home, as it was at or just before this moment
            n_bad_others = n_bad_protected = 0
            lim_tx = []
            srtt, cwnd, unacked, retr = [], [], [], 0.0
            for other, other_rows in by_device.items():
                o = r if other == d else latest(other_rows, times[other], t)
                if o is None:
                    continue
                if other != d and o['_bad']:
                    n_bad_others += 1
                    if o['role'] == 'protected':
                        n_bad_protected += 1
                if other in LIMITABLE:
                    lim_tx.append((o['_tx'], other))
                    retr += o.get('_retr', 0.0)
                    for values, col in ((srtt, 'tcp_srtt_ms'), (cwnd, 'tcp_cwnd'), (unacked, 'tcp_unacked')):
                        v = f(o[col])
                        if v is not None:
                            values.append(v)
            top_tx, top_dev = max(lim_tx) if lim_tx else (None, None)
            total = sum(v for v, _ in lim_tx)
            feat.update({
                'n_bad_others': n_bad_others,
                'n_bad_protected': n_bad_protected,
                'top_tx_kbps': top_tx,
                'top_tx_share': None if top_tx is None else min(top_tx / CAPACITY_KBPS, 2.0),
                'limitable_tx_kbps': total if lim_tx else None,
                'is_top_sender': 1 if top_dev == d else 0,
                'home_tcp_srtt_max': max(srtt) if srtt else None,
                'home_tcp_retrans': retr,
                'home_tcp_cwnd_min': min(cwnd) if cwnd else None,
                'home_tcp_unacked': sum(unacked) if unacked else None,
            })

            lo = bisect.bisect_right(msg_times, t - MQTT_WINDOW_S)
            hi = bisect.bisect_right(msg_times, t)
            recent = msgs[lo:hi]
            feat['home_mqtt_msgs'] = sum(m[1] for m in recent)
            feat['home_mqtt_delay_ms'] = mean([m[2] for m in recent])

            result.append([r[c] for c in META] + [out(feat[c]) for c in FEATURES])
    result.sort(key=lambda x: (float(x[META.index('timestamp')]), x[META.index('device')]))
    return result


def write_rows(path, rows):
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(META + FEATURES)
        w.writerows(rows)


def report(rows):
    """Average of four key features per event type, protected devices only."""
    cols = ['uplink_util', 'rtt_ratio', 'n_bad_others', 'top_tx_share']
    idx = {c: (META + FEATURES).index(c) for c in cols + ['event_type', 'role', 'label_valid']}
    stats = {}
    for r in rows:
        if str(r[idx['label_valid']]) != '1' or r[idx['role']] != 'protected':
            continue
        s = stats.setdefault(r[idx['event_type']], {c: [0.0, 0] for c in cols})
        for c in cols:
            if r[idx[c]] != '':
                s[c][0] += float(r[idx[c]])
                s[c][1] += 1
    print(f"\n{'EVENT TYPE':<12}" + ''.join(f'{c:>15}' for c in cols) + '   (averages, protected devices)')
    for name in sorted(stats):
        print(f'{name:<12}' + ''.join(f'{(v[0] / v[1] if v[1] else 0):>15.2f}' for v in (stats[name][c] for c in cols)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--session', type=int)
    p.add_argument('--all', action='store_true')
    args = p.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)

    if args.all:
        names = sorted(n for n in os.listdir(IN_DIR) if n.startswith('session_') and n.endswith('.csv'))
    elif args.session is not None:
        names = [f'session_{args.session:03d}.csv']
    else:
        p.error('give --session N or --all')

    everything = []
    for name in names:
        rows = build_session(os.path.join(IN_DIR, name))
        write_rows(os.path.join(OUT_DIR, name), rows)
        print(f'{name}: {len(rows)} rows, {len(FEATURES)} features')
        everything += rows
    if args.all:
        write_rows(os.path.join(OUT_DIR, 'all_sessions.csv'), everything)
        print(f'all_sessions.csv: {len(everything)} rows from {len(names)} sessions')
    with open(os.path.join(OUT_DIR, 'feature_list.json'), 'w') as fh:
        json.dump({'basic': BASIC, 'cross_layer': CROSS}, fh, indent=2)
    report(everything)


if __name__ == '__main__':
    main()