#!/usr/bin/env python3
"""
run_experiment.py - one unattended, labelled session saved to data/raw/session_XXX/.
Run from the project root:  sudo python3 -m experiments.run_experiment --session 1
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import time

import topo                                        # adds topo/ to the import path
from mininet.clean import cleanup
from mininet.log import setLogLevel, info

from smart_home_topo import (build_network, start_services, stop_services,
                             PROJECT_ROOT, PORT_MAP_FILE)
from congestion import start_congestion_event, floods_running, EVENT_LOG
from faults import wan_fault, device_link_fault, faults_running
from network_monitor import METRICS_DIR, TCP_DIR, INTERVAL
from mqtt_traffic import LOG_FILE, MQTT_LOG
from normal_traffic import IPERF_UDP_LOG, IPERF_TCP_LOG
from experiments.scenarios import make_schedule, should_act

RAW_DIR = os.path.join(PROJECT_ROOT, 'data', 'raw')
LINK = dict(bw_mbit=10, lan_delay_ms=5, wan_delay_ms=10, loss_pct=0)   # as in smart_home_topo.py
MIN_QUIET_S = 30          # at least this long after the last END before the next event starts


def git_info():
    """Commit hash of the code, and whether there are uncommitted changes."""
    def run(*cmd):
        try:
            return subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True,
                                  text=True, timeout=10).stdout.strip()
        except Exception:
            return ''
    return run('git', 'rev-parse', '--short', 'HEAD') or 'unknown', \
        bool(run('git', 'status', '--porcelain', '--', 'topo', 'experiments'))


def wait_until(t0, offset):
    """Sleep until `offset` seconds after the session start t0."""
    delay = t0 + offset - time.time()
    if delay > 0:
        time.sleep(delay)


def last_event_end():
    """Time of the most recent END line in the events log (None if there is none yet)."""
    try:
        with open(EVENT_LOG) as f:
            ends = [float(line.split(',')[0]) for line in f if line.rstrip().endswith(',end')]
    except (FileNotFoundError, ValueError):
        return None
    return max(ends) if ends else None


def start_event(net, ev):
    """Start one scheduled event with ITS OWN parameters. Returns the events.log event_id."""
    p = ev['params']
    if ev['type'].startswith('C_'):
        return start_congestion_event(net, p['flooders'], p['rate_mbps'],
                                      ev['duration'], ev['type'])
    if ev['type'] == 'F_WAN':
        return wan_fault(net, p['delay_ms'], p['loss_pct'], ev['duration'])
    return device_link_fault(net, p['device'], p['loss_pct'], ev['duration'])


def play_schedule(net, schedule, t0, duration, warnings):
    """Start each event at its planned time, but only after the previous one has ended
    and the network has had MIN_QUIET_S of quiet time to recover."""
    for ev in schedule:
        wait_until(t0, ev['t_start'])
        while floods_running() or faults_running():          # previous event still draining
            time.sleep(1)
        last_end = last_event_end()
        if last_end is not None:
            quiet_left = MIN_QUIET_S - (time.time() - last_end)
            if quiet_left > 0:
                time.sleep(quiet_left)                          # let the devices recover first

        actual = time.time() - t0
        if actual + ev['duration'] > duration:
            warnings.append(f"event {ev['id']} skipped: not enough session time left")
            info(f"*** [{actual:6.0f} s] event {ev['id']} skipped (not enough time left)\n")
            continue

        ev['event_id'] = start_event(net, ev)
        ev['actual_start_s'] = round(actual, 1)
        ev['late_s'] = round(actual - ev['t_start'], 1)
        if ev['late_s'] > 5:
            warnings.append(f"event {ev['id']} started {ev['late_s']} s late")
        info(f"*** [{actual:6.0f} s] event {ev['id']}/{len(schedule)} {ev['type']} "
             f"started ({ev['params']})\n")


def save_session(out_dir, meta, schedule):
    """Copy every log into the session folder, plus events.csv and meta.json."""
    shutil.copytree(METRICS_DIR, f'{out_dir}/network_metrics',
                    ignore=shutil.ignore_patterns('*.ping'))
    shutil.copytree(TCP_DIR, f'{out_dir}/tcp_metrics')
    for path in (LOG_FILE, MQTT_LOG, IPERF_UDP_LOG, IPERF_TCP_LOG, EVENT_LOG, PORT_MAP_FILE):
        if os.path.exists(path):
            shutil.copy(path, out_dir)

    by_id = {str(ev.get('event_id')): ev for ev in schedule}
    with open(EVENT_LOG, newline='') as fin, \
         open(f'{out_dir}/events.csv', 'w', newline='') as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=reader.fieldnames + ['schedule_id', 'should_act'])
        writer.writeheader()
        for row in reader:
            ev = by_id.get(row['event_id'])
            row['schedule_id'] = ev['id'] if ev else ''
            row['should_act'] = should_act(ev) if ev else ''
            writer.writerow(row)

    with open(f'{out_dir}/meta.json', 'w') as f:
        json.dump(meta, f, indent=2)


def run_session(session, seed, duration, n_events, pcap, out_root):
    out_dir = os.path.join(out_root, f'session_{session:03d}')
    if os.path.exists(out_dir):
        raise SystemExit(f'{out_dir} already exists: choose another --session (data is never overwritten)')

    schedule = make_schedule(duration, n_events, seed)
    commit, dirty = git_info()
    warnings = [] if not dirty else ['code has uncommitted changes (git_dirty)']
    info(f'*** Session {session}: seed {seed}, {duration} s, {len(schedule)} events, '
         f'commit {commit}\n')

    cleanup()                                        # same as: sudo mn -c
    net, hosts, cloud, router = build_network()
    net.start()
    complete = False
    t0 = time.time()                                 # defined before anything can fail
    try:
        start_services(net, hosts, cloud, router, seed, pcap)
        t0 = time.time()                             # session clock starts once services run
        play_schedule(net, schedule, t0, duration, warnings)
        wait_until(t0, duration)                     # recovery time after the last event
        complete = True
    except KeyboardInterrupt:
        warnings.append('interrupted with Ctrl+C')
    finally:
        t_end = time.time()
        stop_services(hosts, cloud, router, pcap)
        net.stop()

    for ev in schedule:
        ev['should_act'] = should_act(ev)
    meta = dict(session=session, seed=seed, complete=complete,
                start=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t0)),
                duration_planned_s=duration, duration_actual_s=round(t_end - t0, 1),
                interval_s=INTERVAL, link=LINK, pcap=pcap, min_quiet_s=MIN_QUIET_S,
                git_commit=commit, git_dirty=dirty,
                n_events=len(schedule),
                n_events_played=sum('event_id' in ev for ev in schedule),
                schedule=schedule, warnings=warnings)
    os.makedirs(out_dir)
    save_session(out_dir, meta, schedule)
    info(f'*** Saved {out_dir}  (complete={complete}, {len(warnings)} warning(s))\n')
    return out_dir


def main():
    ap = argparse.ArgumentParser(description='Run one unattended, labelled session')
    ap.add_argument('--session', type=int, required=True, help='session number (folder name)')
    ap.add_argument('--seed', type=int, help='default: same as --session')
    ap.add_argument('--duration', type=int, default=1800, help='seconds (default 1800 = 30 min)')
    ap.add_argument('--events', type=int, default=12, help='max events; 0 = normal-only session')
    ap.add_argument('--pcap', action='store_true', help='also record packet captures (large!)')
    ap.add_argument('--out', default=RAW_DIR, help='output folder (default data/raw)')
    args = ap.parse_args()

    if os.geteuid() != 0:
        raise SystemExit('Run with sudo (Mininet needs root).')
    setLogLevel('info')
    run_session(args.session, args.seed if args.seed is not None else args.session,
                args.duration, args.events, args.pcap, args.out)


if __name__ == '__main__':
    main()