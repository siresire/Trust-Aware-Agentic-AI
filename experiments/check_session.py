#!/usr/bin/env python3
"""
check_session.py - quick quality check of one recorded session folder.
Usage (project root, no sudo):  python3 -m experiments.check_session data/raw/session_001
"""

import csv
import glob
import json
import os
import sys

PROTECTED = ('camera', 'doorbell', 'lock', 'thermostat', 'speaker', 'light', 'plug')


def load_metrics(d):
    """{device: rows with ping data}, plus the number of rows with the wrong column count."""
    logs, bad = {}, 0
    for f in sorted(glob.glob(f'{d}/network_metrics/*.log')):
        with open(f) as fh:
            lines = fh.read().splitlines()
        bad += sum(1 for line in lines[1:] if line.count(',') != 6)
        rows = [r for r in csv.DictReader(lines) if None not in r and r['loss_pct'] not in ('NA', '')]
        logs[os.path.basename(f)[:-4]] = rows
    return logs, bad


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: python3 -m experiments.check_session <session folder>')
    d = sys.argv[1].rstrip('/')
    meta = json.load(open(f'{d}/meta.json'))
    events = list(csv.DictReader(open(f'{d}/events.csv')))
    logs, bad = load_metrics(d)

    print(f"{d}: seed {meta['seed']}, {meta['duration_actual_s']:.0f} s, complete={meta['complete']}, "
          f"commit {meta['git_commit']}, dirty={meta['git_dirty']}")
    print(f"rows with wrong column count: {bad}")
    for w in meta['warnings']:
        print(f"WARNING: {w}")

    normal = {dev: sorted(float(r['rtt_ms']) for r in rows if r['rtt_ms'] != 'NA')
              for dev, rows in logs.items() if dev in PROTECTED}
    normal = {dev: v[len(v) // 4] for dev, v in normal.items() if v}      # low quartile = calm RTT

    for ev in meta['schedule']:
        mine = [r for r in events if r['event_id'] == str(ev.get('event_id'))]
        starts = sum(r['phase'] == 'start' for r in mine)
        ends = sum(r['phase'] == 'end' for r in mine)
        if 'event_id' not in ev:
            print(f"\nevent {ev['id']} {ev['type']}: not played (session ended before it)")
            continue
        if not mine:
            print(f"\nevent {ev['id']} {ev['type']}: PLAYED BUT MISSING from events.csv  <-- problem")
            continue
        t = [float(r['timestamp']) for r in mine]
        start, end = min(t), max(t)
        print(f"\nevent {ev['id']} {ev['type']} {ev['params']}  planned {ev['duration']} s, "
              f"real {end - start:.0f} s, late {ev.get('late_s')} s, start/end {starts}/{ends}, "
              f"should_act {ev['should_act']}")
        for dev in PROTECTED:
            rows = logs.get(dev, [])
            dur = [r for r in rows if start <= float(r['timestamp']) <= end]
            loss = sum(float(r['loss_pct']) for r in dur) / max(len(dur), 1)
            rtts = [float(r['rtt_ms']) for r in dur if r['rtt_ms'] != 'NA']
            rtt = f"{sum(rtts) / len(rtts):6.1f}" if rtts else '     -'
            back = next((float(r['timestamp']) - end for r in rows
                         if float(r['timestamp']) > end and float(r['loss_pct']) == 0
                         and r['rtt_ms'] != 'NA' and float(r['rtt_ms']) < 1.5 * normal.get(dev, 60)),
                        None)
            print(f"  {dev:<11} loss {loss:5.1f} %   rtt {rtt} ms (normal ~{normal.get(dev, 0):.0f})   "
                  f"normal again {'never' if back is None else f'{back:.0f} s after END'}")


if __name__ == '__main__':
    main()