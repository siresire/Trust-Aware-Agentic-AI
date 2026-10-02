#!/usr/bin/env python3
"""
baseline.py - what "normal" looks like for every IoT device, from the normal-only sessions.
Prints a report and a `thresholds:` block to paste into config.yaml.
Run from the project root (no sudo):  python3 -m experiments.baseline
"""

import argparse
import csv
import glob
import json
import os

import topo                                    # adds topo/ to the import path
from smart_home_topo import DEVICES, PROJECT_ROOT
from mqtt_traffic import MQTT_PROFILES
from mqtt_delay import read_log

RAW_DIR = os.path.join(PROJECT_ROOT, 'data', 'raw')
WARMUP_S = 30                                  # skip the first seconds of every session


def pct(values, p):
    """The p-th percentile of a list (None if the list is empty)."""
    s = sorted(values)
    if not s:
        return None
    k = (len(s) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def show(value, digits=1):
    return '-' if value is None else f'{value:.{digits}f}'


def normal_sessions(raw_dir):
    """Folders of complete sessions that were recorded with no events."""
    found = []
    for d in sorted(glob.glob(f'{raw_dir}/session_*')):
        try:
            with open(f'{d}/meta.json') as f:
                meta = json.load(f)
        except FileNotFoundError:
            continue
        if meta['complete'] and meta['n_events'] == 0:
            found.append(d)
    return found


def read_rows(path):
    """Rows of one metrics log, without the warm-up and without half-written lines."""
    with open(path, newline='') as f:
        rows = [r for r in csv.DictReader(f) if None not in r and None not in r.values()]
    if not rows:
        return []
    t0 = float(rows[0]['timestamp'])
    return [r for r in rows if float(r['timestamp']) - t0 >= WARMUP_S]


def main():
    ap = argparse.ArgumentParser(description='Per-device baseline from normal-only sessions')
    ap.add_argument('--raw', default=RAW_DIR, help='folder with session_XXX folders')
    args = ap.parse_args()

    sessions = normal_sessions(args.raw)
    if not sessions:
        raise SystemExit(f'No complete normal-only sessions in {args.raw} '
                         f'(record some with --events 0)')
    print(f"Normal-only sessions: {', '.join(os.path.basename(d) for d in sessions)}  "
          f"(first {WARMUP_S} s of each skipped)\n")

    # ---- per device: RTT, jitter, loss ----
    rtt_p99, loss_rows = {}, {}
    print(f"{'DEVICE':<11}{'ROWS':>6}{'RTT p50':>9}{'p95':>8}{'p99':>8}{'max':>8}"
          f"{'JIT p99':>9}{'LOSS>0 %':>10}{'NO REPLY %':>12}")
    for name, _ip in DEVICES:
        rows = []
        for d in sessions:
            rows += read_rows(f'{d}/network_metrics/{name}.log')
        rtt = [float(r['rtt_ms']) for r in rows if r['rtt_ms'] != 'NA']
        jit = [float(r['jitter_ms']) for r in rows if r['jitter_ms'] != 'NA']
        lossy = sum(1 for r in rows if r['loss_pct'] != 'NA' and float(r['loss_pct']) > 0)
        silent = sum(1 for r in rows if r['rtt_ms'] == 'NA')
        n = max(len(rows), 1)
        rtt_p99[name] = pct(rtt, 99)
        loss_rows[name] = 100 * lossy / n
        print(f"{name:<11}{len(rows):>6}{show(pct(rtt, 50)):>9}{show(pct(rtt, 95)):>8}"
              f"{show(pct(rtt, 99)):>8}{show(max(rtt) if rtt else None):>8}"
              f"{show(pct(jit, 99), 2):>9}{100 * lossy / n:>10.2f}{100 * silent / n:>12.2f}")

    # ---- do the sessions agree with each other? ----
    print(f"\n{'SESSION':<14}{'RTT p50':>9}{'RTT p99':>9}{'LOSS>0 %':>10}   (all devices together)")
    for d in sessions:
        rows = []
        for name, _ip in DEVICES:
            rows += read_rows(f'{d}/network_metrics/{name}.log')
        rtt = [float(r['rtt_ms']) for r in rows if r['rtt_ms'] != 'NA']
        lossy = sum(1 for r in rows if r['loss_pct'] != 'NA' and float(r['loss_pct']) > 0)
        print(f"{os.path.basename(d):<14}{show(pct(rtt, 50)):>9}{show(pct(rtt, 99)):>9}"
              f"{100 * lossy / max(len(rows), 1):>10.2f}")

    # ---- shared uplink ----
    up = []
    for d in sessions:
        up += [float(r['rx_kbps']) for r in read_rows(f'{d}/network_metrics/router_lan.log')]
    print(f"\nShared uplink (kbps): p50 {show(pct(up, 50), 0)}, p95 {show(pct(up, 95), 0)}, "
          f"p99 {show(pct(up, 99), 0)}, max {show(max(up) if up else None, 0)}")

    # ---- MQTT delivery delay per sensor ----
    mqtt_p99 = {}
    print(f"\n{'SENSOR':<11}{'MSGS':>6}{'DELAY p50':>11}{'p99':>9}{'max':>9}{'MISSING':>9}")
    for name in MQTT_PROFILES:
        delays, missing = [], 0
        for d in sessions:
            dl, sq = read_log(f'{d}/mqtt_received.log')
            delays += dl.get(name, [])
            unique = set(sq.get(name, []))
            missing += max(unique) - len(unique) if unique else 0
        mqtt_p99[name] = pct(delays, 99)
        print(f"{name:<11}{len(delays):>6}{show(pct(delays, 50)):>11}{show(pct(delays, 99)):>9}"
              f"{show(max(delays) if delays else None):>9}{missing:>9}")

    # ---- block for config.yaml ----
    print("\n# ---- paste into config.yaml ----")
    print("thresholds:")
    print("  rtt_p99_ms:")
    for name, v in rtt_p99.items():
        print(f"    {name}: {show(v)}")
    print("  normal_loss_rows_pct:")
    for name, v in loss_rows.items():
        print(f"    {name}: {v:.2f}")
    print("  mqtt_delay_p99_ms:")
    for name, v in mqtt_p99.items():
        print(f"    {name}: {show(v)}")


if __name__ == '__main__':
    main()