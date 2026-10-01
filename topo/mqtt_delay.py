#!/usr/bin/env python3
"""
mqtt_delay.py - application-level view of the MQTT sensors.
Reads /tmp/mqtt_received.log and prints, per sensor: messages received, missing,
duplicates, and delivery delay (min / avg / max / last).
Run in a normal terminal (no sudo):  python3 topo/mqtt_delay.py
"""

import sys
from collections import defaultdict

MQTT_LOG = '/tmp/mqtt_received.log'


def parse_payload(payload):
    """'seq=5;ts=17.5;temp=21' -> {'seq': '5', 'ts': '17.5', 'temp': '21'}"""
    fields = {}
    for part in payload.split(';'):
        if '=' in part:
            key, value = part.split('=', 1)
            fields[key] = value
    return fields


def read_log(path):
    """Return {device: [delays in ms]} and {device: [seq numbers]} from the received log."""
    delays = defaultdict(list)
    seqs = defaultdict(list)
    with open(path) as f:
        for line in f:
            parts = line.strip().split(',', 2)
            if len(parts) < 3:
                continue
            arrival, topic, payload = parts
            fields = parse_payload(payload)
            if 'seq' not in fields or 'ts' not in fields:
                continue                               # e.g. a manual test message like 'hello'
            try:
                delay_ms = (float(arrival) - float(fields['ts'])) * 1000
                seq = int(fields['seq'])
            except ValueError:
                continue                               # half-written or malformed line
            device = topic.split('/')[1]               # home/lock/telemetry -> lock
            delays[device].append(delay_ms)
            seqs[device].append(seq)
    return delays, seqs


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else MQTT_LOG
    try:
        delays, seqs = read_log(path)
    except FileNotFoundError:
        print(f'No log at {path} (is the network running?)')
        return
    if not delays:
        print('No labelled MQTT messages yet.')
        return

    print(f"{'DEVICE':<12}{'RECV':>6}{'MISSING':>9}{'DUPS':>6}"
          f"{'MIN_ms':>9}{'AVG_ms':>9}{'MAX_ms':>9}{'LAST_ms':>9}")
    for device in sorted(delays):
        d = delays[device]
        s = seqs[device]
        unique = set(s)
        missing = max(unique) - len(unique)
        dups = len(s) - len(unique)
        print(f"{device:<12}{len(unique):>6}{missing:>9}{dups:>6}"
              f"{min(d):>9.1f}{sum(d)/len(d):>9.1f}{max(d):>9.1f}{d[-1]:>9.1f}")


if __name__ == '__main__':
    main()