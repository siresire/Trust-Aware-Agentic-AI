#!/usr/bin/env python3
"""
network_dashboard.py - live terminal view of every IoT device and the shared uplink.
Reads the logs written by topo/ while the network runs (no sudo needed).
Run from the project root:  python3 -m dashboards.network_dashboard   (Ctrl+C to quit)
"""

import argparse
import csv
import statistics
import time

import topo                                          # adds topo/ to the import path
from network_monitor import METRICS_DIR, INTERVAL    # /tmp/network_metrics, 2 s
from congestion import EVENT_LOG, ALLOWED_FLOODERS   # /tmp/events.log, laptop/phone/tv
from smart_home_topo import DEVICES                  # the 10 IoT devices, in order

LINK_KBPS = 10000          # shared uplink capacity (10 Mbit/s)
PERSIST = 3                # a status needs this many bad samples in a row (3 x 2 s = 6 s)
WARN_X, CRIT_X = 1.5, 3.0  # RTT above 1.5x / 3x the device's own baseline
RECOVERY_S = 30            # rows this long after an event are not used for the baseline
MIN_BASELINE_ROWS = 10     # quiet rows needed before a device is judged

USE_COLOR = True
COLORS = dict(green='\033[32m', yellow='\033[33m', red='\033[31m', cyan='\033[36m',
              dim='\033[2m', bold='\033[1m')


def paint(text, color):
    """Colour text for the terminal (or leave it plain with --no-color)."""
    if not USE_COLOR or not color:
        return text
    return f"{COLORS[color]}{text}\033[0m"


def num(value):
    """'61.2' -> 61.2 ; 'NA', '' or None -> None"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt(value, digits=0):
    """Number as text, or '-' when there is no value."""
    return '-' if value is None else f'{value:.{digits}f}'


def bar(frac, width=30):
    """A text bar: 0.31 -> █████████·····················"""
    n = max(0, min(width, round(frac * width)))
    return '█' * n + '·' * (width - n)


def read_csv(path):
    """All complete rows of a CSV log as dicts ([] if the file does not exist yet)."""
    try:
        with open(path, newline='') as f:
            return [r for r in csv.DictReader(f)
                    if None not in r and None not in r.values()]
    except FileNotFoundError:
        return []


def read_events(path=EVENT_LOG):
    """Group events.log lines by event: type, targets, start, end, still-running targets."""
    events = {}
    for r in read_csv(path):
        ts = num(r['timestamp'])
        if ts is None:
            continue
        e = events.setdefault(r['event_id'], dict(
            type=r['event_type'], params=r['params'], duration=num(r['duration_s']),
            targets=set(), open=set(), start=None, end=None))
        if r['phase'] == 'start':
            e['targets'].add(r['device'])
            e['open'].add(r['device'])
            e['start'] = ts if e['start'] is None else min(e['start'], ts)
        elif r['phase'] == 'end':
            e['open'].discard(r['device'])
            e['end'] = ts if e['end'] is None else max(e['end'], ts)
    return sorted((e for e in events.values() if e['start']), key=lambda e: e['start'])


def event_windows(events, now):
    """(start, end) of every event; a running event ends 'now'."""
    return [(e['start'], now if e['open'] else e['end']) for e in events]


def in_any_window(ts, windows, pad=RECOVERY_S):
    """True if ts falls inside an event or its recovery time."""
    return any(start <= ts <= end + pad for start, end in windows)


def baseline_rtt(rows, windows):
    """Median RTT of this device's rows recorded outside every event (+ recovery)."""
    quiet = []
    for r in rows:
        ts, rtt = num(r['timestamp']), num(r['rtt_ms'])
        if ts is not None and rtt is not None and not in_any_window(ts, windows):
            quiet.append(rtt)
    if len(quiet) < MIN_BASELINE_ROWS:
        return None
    return statistics.median(quiet)


def sample_level(row, base):
    """0 = fine, 1 = warning, 2 = critical, for ONE 2-second sample."""
    rtt, loss = num(row['rtt_ms']), num(row['loss_pct']) or 0
    if rtt is None or loss >= 66 or rtt > CRIT_X * base:
        return 2
    if loss > 0 or rtt > WARN_X * base:
        return 1
    return 0


def device_status(rows, base, now):
    """Status from the last PERSIST samples: the weakest of them decides."""
    if not rows:
        return 'NO DATA', 'dim'
    if now - num(rows[-1]['timestamp']) > 3 * INTERVAL + 2:
        return 'STALE', 'dim'
    if base is None:
        return 'LEARNING', 'cyan'
    level = min(sample_level(r, base) for r in rows[-PERSIST:])
    return [('OK', 'green'), ('WARN', 'yellow'), ('CRIT', 'red')][level]


def render(now):
    """Build one full screen of text."""
    events = read_events()
    windows = event_windows(events, now)
    running = [e for e in events if e['open']]
    lines = [paint(f"Smart-home IoT network — live   {time.strftime('%H:%M:%S')}", 'bold'), '']

    # --- shared uplink: total upload of all home devices (router home side) ---
    lan = read_csv(f'{METRICS_DIR}/router_lan.log')
    up = num(lan[-1]['rx_kbps']) if lan else None
    frac = (up or 0) / LINK_KBPS
    color = 'green' if frac < 0.7 else 'yellow' if frac < 0.9 else 'red'
    lines += [f"Shared uplink  {paint(bar(frac), color)}  {fmt(up)} / {LINK_KBPS} kbps  "
              f"({frac:.0%})", '']

    # --- one row per IoT device ---
    notes = {}
    for e in running:
        for d in e['targets']:
            notes[d] = 'flooding' if e['type'].startswith('C_') else 'fault on its link'
    lines.append(paint(f"{'DEVICE':<11}{'ROLE':<10}{'TX kbps':>8}{'RX kbps':>8}{'RTT ms':>8}"
                       f"{'BASE':>7}{'JITTER':>8}{'LOSS%':>7}  {'STATUS':<9}NOTE", 'bold'))
    for name, _ip in DEVICES:
        rows = read_csv(f'{METRICS_DIR}/{name}.log')
        last = rows[-1] if rows else {}
        base = baseline_rtt(rows, windows)
        status, scolor = device_status(rows, base, now)
        role = 'limitable' if name in ALLOWED_FLOODERS else 'protected'
        lines.append(
            f"{name:<11}{role:<10}{fmt(num(last.get('tx_kbps'))):>8}"
            f"{fmt(num(last.get('rx_kbps'))):>8}{fmt(num(last.get('rtt_ms')), 1):>8}"
            f"{fmt(base, 1):>7}{fmt(num(last.get('jitter_ms')), 2):>8}"
            f"{fmt(num(last.get('loss_pct'))):>7}  {paint(f'{status:<9}', scolor)}"
            f"{notes.get(name, '')}")

    # --- events: running ones, then the last 5 finished ---
    lines += ['', paint('Events', 'bold')]
    if not running:
        lines.append(paint('  none running', 'dim'))
    for e in running:
        act = 'should act: YES' if e['type'].startswith('C_') else 'should act: NO (decoy)'
        lines.append(f"  ▶ {e['type']:<10}{','.join(sorted(e['targets'])):<20}"
                     f"{e['params']:<30}{now - e['start']:>4.0f}/{fmt(e['duration'])} s   {act}")
    for e in [e for e in events if not e['open']][-5:]:
        lines.append(paint(f"    {e['type']:<10}{','.join(sorted(e['targets'])):<20}"
                           f"{e['end'] - e['start']:>4.0f} s, ended {now - e['end']:.0f} s ago",
                           'dim'))

    lines += ['', paint(f"Status needs {PERSIST} bad samples in a row ({PERSIST * INTERVAL} s). "
                        f"WARN: RTT > {WARN_X}x BASE or any loss. CRIT: RTT > {CRIT_X}x BASE, "
                        f"loss >= 66 % or no reply.", 'dim'),
              paint("BASE = the device's median RTT outside events. Ctrl+C to quit.", 'dim')]
    return '\n'.join(lines)


def main():
    global USE_COLOR
    ap = argparse.ArgumentParser(description='Live smart-home IoT network dashboard')
    ap.add_argument('--once', action='store_true', help='print one frame and exit')
    ap.add_argument('--no-color', action='store_true', help='plain text (e.g. to save to a file)')
    args = ap.parse_args()
    USE_COLOR = not args.no_color

    if args.once:
        print(render(time.time()))
        return
    try:
        while True:
            print('\033[H\033[2J' + render(time.time()), flush=True)
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print()


if __name__ == '__main__':
    main()