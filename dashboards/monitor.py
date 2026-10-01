#!/usr/bin/env python3
"""
monitor.py - live feed of who is sending what, MQTT delivery health, and labelled events.
Read-only (no sudo). Run from the project root:  python3 -m dashboards.monitor
"""

import argparse
import statistics
import time

import topo                                                   # adds topo/ to the import path
from mqtt_traffic import LOG_FILE, MQTT_PROFILES              # sent log, sensor profiles
from mqtt_delay import read_log, MQTT_LOG                     # delivery delays (Step 14)
from normal_traffic import UDP_PROFILES, TCP_PROFILES, STREAM_PROFILES
from network_monitor import METRICS_DIR, INTERVAL
from congestion import EVENT_LOG
from smart_home_topo import DEVICES
import dashboards.network_dashboard as nd                     # reuse Step 19's helpers
from dashboards.network_dashboard import paint, num, fmt, read_csv, read_events

FEED_LINES = 14          # how many feed lines to show
WINDOW_S = 60            # "last 60 s" for the per-device counts
AVG_SAMPLES = 5          # 5 x 2 s = 10-second average for TX
MQTT_CAP_KBPS = 50       # MQTT sensors send a few bytes; anything sustained above 50 kbps is odd
BURSTY_X, STREAM_X = 0.8, 1.3

nd.COLORS['magenta'] = '\033[35m'
PROTO_COLOR = {'mqtt': 'cyan', 'udp': 'yellow', 'tcp': 'green'}


def rate_kbps(rate):
    """'3M' -> 3000.0 ; '500K' -> 500.0"""
    unit = rate[-1].upper()
    return float(rate[:-1]) * (1000 if unit == 'M' else 1)


def device_info():
    """Return {device: cap_kbps}, {device: protocol} built from the traffic profiles."""
    caps = {name: MQTT_CAP_KBPS for name in MQTT_PROFILES}
    protos = {name: 'mqtt' for name in MQTT_PROFILES}
    for profiles, proto in ((UDP_PROFILES, 'udp'), (TCP_PROFILES, 'tcp'),
                            (STREAM_PROFILES, 'tcp')):
        for name, p in profiles.items():
            caps[name] = rate_kbps(p['rate'])
            protos[name] = proto
    return caps, protos


def read_traffic(path=LOG_FILE):
    """normal_traffic.log has no header: time,device,protocol,size,kind"""
    out = []
    try:
        with open(path) as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) != 5 or num(parts[0]) is None:
                    continue                                  # half-written line
                out.append(dict(t=float(parts[0]), device=parts[1], proto=parts[2],
                                size=parts[3], kind=parts[4]))
    except FileNotFoundError:
        pass
    return out


def size_kb(size):
    """'1463K' -> 1463 ; '41B' -> 0.04 ; a stream rate like '2M' -> None"""
    if size.endswith('K'):
        return num(size[:-1])
    if size.endswith('B'):
        value = num(size[:-1])
        return value / 1024 if value is not None else None
    return None


def feed_items(traffic):
    """(time, text, colour) for recent traffic lines AND every event START/END line."""
    items = [(x['t'], f"{x['device']:<11}{x['proto']:<5}{x['size']:>7}  {x['kind']}",
              PROTO_COLOR.get(x['proto'])) for x in traffic[-FEED_LINES:]]
    for r in read_csv(EVENT_LOG):
        t = num(r['timestamp'])
        if t is None:
            continue
        mark = '▶ START' if r['phase'] == 'start' else '■ END  '
        color = 'red' if r['event_type'].startswith('C_') else 'magenta'
        items.append((t, f"{mark} {r['event_type']:<10}{r['device']:<11}{r['params']}", color))
    return sorted(items)[-FEED_LINES:]


def device_rows(traffic, now, caps, protos):
    """One line per IoT device: messages and KB sent in the last minute, 10-s TX, flag."""
    lines = [paint(f"{'DEVICE':<11}{'PROTO':<7}{'SENT':>5}{'KB':>7}{'TX avg 10s':>12}"
                   f"{'CAP kbps':>10}  FLAG", 'bold')]
    recent = [x for x in traffic if now - x['t'] <= WINDOW_S]
    for name, _ip in DEVICES:
        mine = [x for x in recent if x['device'] == name]
        kb = sum(size_kb(x['size']) or 0 for x in mine)
        tx = [num(r['tx_kbps']) for r in read_csv(f'{METRICS_DIR}/{name}.log')[-AVG_SAMPLES:]]
        tx = [v for v in tx if v is not None]
        avg = sum(tx) / len(tx) if tx else None
        limit = (STREAM_X if name in STREAM_PROFILES else BURSTY_X) * caps[name]
        high = avg is not None and len(tx) == AVG_SAMPLES and avg > limit
        sent = 'stream' if name in STREAM_PROFILES else str(len(mine))
        lines.append(f"{name:<11}{protos[name]:<7}{sent:>5}{kb:>7.0f}{fmt(avg):>12}"
                     f"{caps[name]:>10.0f}  {paint('SUSTAINED HIGH', 'red') if high else ''}")
    return lines


def mqtt_rows():
    """One line per MQTT sensor: QoS, received, missing, duplicates, last vs median delay."""
    lines = [paint(f"{'SENSOR':<11}{'QoS':>4}{'RECV':>6}{'MISSING':>9}{'DUPS':>6}"
                   f"{'LAST ms':>9}{'MEDIAN ms':>11}", 'bold')]
    try:
        delays, seqs = read_log(MQTT_LOG)
    except FileNotFoundError:
        delays, seqs = {}, {}
    for name, profile in MQTT_PROFILES.items():
        d, s = delays.get(name, []), seqs.get(name, [])
        if not d:
            lines.append(paint(f"{name:<11}{profile['qos']:>4}  no messages yet", 'dim'))
            continue
        unique = set(s)
        missing, dups = max(unique) - len(unique), len(s) - len(unique)
        med, last = statistics.median(d), d[-1]
        color = 'red' if last > 5 * med else 'yellow' if last > 2 * med else 'green'
        lines.append(f"{name:<11}{profile['qos']:>4}{len(unique):>6}{missing:>9}{dups:>6}"
                     f"{paint(f'{last:>9.1f}', color)}{med:>11.1f}")
    return lines


def render(now):
    caps, protos = device_info()
    traffic = read_traffic()
    lines = [paint(f"Smart-home traffic & events — live   {time.strftime('%H:%M:%S')}", 'bold'),
             '', paint('Running event', 'bold')]

    running = [e for e in read_events() if e['open']]
    if not running:
        lines.append(paint('  none', 'dim'))
    for e in running:
        act = 'should act: YES' if e['type'].startswith('C_') else 'should act: NO (decoy)'
        lines.append(f"  ▶ {e['type']:<10}{','.join(sorted(e['targets'])):<20}{e['params']:<30}"
                     f"{now - e['start']:>4.0f}/{fmt(e['duration'])} s   {act}")

    lines += ['', paint('Live feed (newest last)', 'bold')]
    for t, text, color in feed_items(traffic):
        lines.append(f"  {time.strftime('%H:%M:%S', time.localtime(t))}  {paint(text, color)}")

    lines += ['', paint(f'Traffic per device (last {WINDOW_S} s)', 'bold')]
    lines += device_rows(traffic, now, caps, protos)
    lines += ['', paint('MQTT delivery', 'bold')]
    lines += mqtt_rows()
    lines += ['', paint(f"SENT/KB = normal traffic sent (sent log). TX avg = measured on the card, "
                        f"floods included. SUSTAINED HIGH: 10-s average > {BURSTY_X}x cap "
                        f"({STREAM_X}x for streams). Ctrl+C to quit.", 'dim')]
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description='Live smart-home traffic and events monitor')
    ap.add_argument('--once', action='store_true', help='print one frame and exit')
    ap.add_argument('--no-color', action='store_true', help='plain text')
    args = ap.parse_args()
    nd.USE_COLOR = not args.no_color          # paint() lives in network_dashboard

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