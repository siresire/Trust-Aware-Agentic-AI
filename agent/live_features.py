"""
live_features.py - the model's 28 features, built live from the running network.
It reuses the training code (ml/merge_logs.py, ml/label.py, ml/features.py)
without changing it, so live features are built exactly like the training ones.

Run from the project root, with the network running:
    python -m agent.live_features --once     # one full table of all 28 features
    python -m agent.live_features            # one summary line every 2 seconds
"""
import argparse
import csv
import json
import os
import time

import pandas as pd

from ml import merge_logs, label, features

LIVE_DIR = 'data/live/session'          # looks like a recorded session folder
MERGED = 'data/live/merged.csv'         # what merge_logs makes
LABELLED = 'data/live/labelled.csv'     # what label adds ('bad' and the threshold)
INTERVAL = 2                            # seconds, same as the monitor


def make_live_folder():
    """A session folder whose logs are the live /tmp logs (links, not copies)."""
    os.makedirs(LIVE_DIR, exist_ok=True)
    with open(os.path.join(LIVE_DIR, 'meta.json'), 'w') as f:
        json.dump({'session': 0, 'seed': 0, 'interval_s': INTERVAL}, f)
    links = {'network_metrics': '/tmp/network_metrics',
             'tcp_metrics': '/tmp/tcp_metrics',
             'mqtt_received.log': '/tmp/mqtt_received.log'}
    for name, target in links.items():
        path = os.path.join(LIVE_DIR, name)
        if not os.path.islink(path):
            os.symlink(target, path)


def build_now(thresholds):
    """merge -> label -> features on the live logs; the newest row of each device."""
    rows = merge_logs.merge_session(LIVE_DIR)
    if not rows:
        return None
    merge_logs.write_rows(MERGED, rows)

    cols, rows = label.label_session(MERGED, thresholds)
    with open(LABELLED, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols + label.NEW_COLS)
        w.writeheader()
        w.writerows(rows)

    rows = features.build_session(LABELLED)
    df = pd.DataFrame(rows, columns=features.META + features.FEATURES)
    df['timestamp'] = df['timestamp'].astype(float)
    df[features.FEATURES] = df[features.FEATURES].apply(pd.to_numeric, errors='coerce')
    newest = df.sort_values('timestamp').groupby('device').tail(1)
    return newest.set_index('device')


def summary(now, ms):
    """One line: the shared link, the top sender, the worst protected device."""
    age = time.time() - now['timestamp'].max()
    link = now['uplink_util'].max()
    lim = now[now['is_protected'] == 0]          # phone, tv, laptop
    top = lim['tx_kbps'].idxmax()
    prot = now[now['is_protected'] == 1]
    worst = prot['rtt_ratio'].idxmax()
    print(f"{time.strftime('%H:%M:%S')}  link {link:4.2f}  "
          f"top sender {top:6s} {lim.loc[top, 'tx_kbps']:6.0f} kbit/s  "
          f"worst protected {worst:10s} rtt_ratio {prot.loc[worst, 'rtt_ratio']:5.2f}  "
          f"max loss {prot['loss_pct'].max():5.1f} %  "
          f"({ms:.0f} ms to build, data {age:.1f} s old)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--once', action='store_true', help='print one full table and stop')
    args = p.parse_args()

    make_live_folder()
    thresholds = label.read_thresholds(label.CONFIG)
    pd.set_option('display.width', 200)

    while True:
        t = time.time()
        now = build_now(thresholds)
        ms = (time.time() - t) * 1000
        if now is None:
            print('no live logs yet - is the network running?')
        elif args.once:
            print(now[features.FEATURES].T.to_string())
            print(f'\n{len(now)} devices, {len(features.FEATURES)} features, built in {ms:.0f} ms')
        else:
            summary(now, ms)
        if args.once:
            break
        time.sleep(max(0, INTERVAL - (time.time() - t)))


if __name__ == '__main__':
    main()