"""
Adds to each merged row:
  rtt_thr_ms    the device's own threshold (from config.yaml)
  bad           this single reading is bad (slow, or a ping was lost)
  degraded      the device is in trouble now (2 of the last 3 readings bad)
  will_degrade  the device is degraded at some point in the next 6 seconds
  onset         will_degrade is 1 but the device is still fine now
  label_valid   0 for rows that must not be used (start-up, end of session)

    python3 -m ml.label --session 1
    python3 -m ml.label --all
"""
import argparse
import csv
import os

IN_DIR = 'data/merged'
OUT_DIR = 'data/labelled'
CONFIG = 'config.yaml'

HORIZON_S = 6.0          # how far ahead we look
WARMUP_S = 30.0          # start-up traffic, not used
NEED_BAD = 2             # this many bad readings ...
OUT_OF = 3               # ... out of the last this many = degraded

NEW_COLS = ['rtt_thr_ms', 'bad', 'degraded', 'will_degrade', 'onset', 'label_valid']


def read_thresholds(path):
    """Read the rtt_p99_ms block of config.yaml -> {device: threshold}."""
    thr = {}
    inside = False
    block_indent = 0
    with open(path) as f:
        for line in f:
            if not line.strip() or line.strip().startswith('#'):
                continue
            indent = len(line) - len(line.lstrip())
            if line.strip() == 'rtt_p99_ms:':
                inside = True
                block_indent = indent
                continue
            if inside:
                if indent <= block_indent:
                    break
                name, value = line.strip().split(':')
                thr[name.strip()] = float(value)
    if not thr:
        raise SystemExit(f'no rtt_p99_ms thresholds found in {path}')
    return thr


def is_bad(row, thr):
    """One reading is bad if a ping was lost, there was no reply, or it was too slow."""
    if row['rtt_ms'] == '':
        return 1
    if row['loss_pct'] != '' and float(row['loss_pct']) > 0:
        return 1
    if float(row['rtt_ms']) > thr:
        return 1
    return 0


def label_device(rows, thr, t_end):
    """rows = all rows of one device in one session, in time order."""
    n = len(rows)
    times = [float(r['timestamp']) for r in rows]
    for r in rows:
        r['rtt_thr_ms'] = thr
        r['bad'] = is_bad(r, thr)
    for i, r in enumerate(rows):
        recent = rows[max(0, i - OUT_OF + 1):i + 1]
        r['degraded'] = 1 if sum(x['bad'] for x in recent) >= NEED_BAD else 0
    j = 0
    for i, r in enumerate(rows):
        j = max(j, i + 1)
        while j < n and times[j] <= times[i] + HORIZON_S:
            j += 1
        future = rows[i + 1:j]
        r['will_degrade'] = 1 if any(x['degraded'] for x in future) else 0
        r['onset'] = 1 if r['will_degrade'] and not r['degraded'] else 0
        ok = float(r['t_s']) >= WARMUP_S and times[i] + HORIZON_S <= t_end
        r['label_valid'] = 1 if ok else 0


def label_session(path, thresholds):
    with open(path) as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames
        rows = list(reader)
    if not rows:
        return cols, rows
    t_end = max(float(r['timestamp']) for r in rows)
    by_device = {}
    for r in rows:
        by_device.setdefault(r['device'], []).append(r)
    for device, dev_rows in by_device.items():
        dev_rows.sort(key=lambda r: float(r['timestamp']))
        label_device(dev_rows, thresholds[device], t_end)
    return cols, rows


def pct(part, whole):
    return f'{100.0 * part / whole:5.1f} %' if whole else '    - '


def report(rows):
    """How often are protected devices degraded, per event type?"""
    stats = {}
    for r in rows:
        if r['label_valid'] != 1 or r['role'] != 'protected':
            continue
        s = stats.setdefault(r['event_type'], [0, 0, 0, 0])
        s[0] += 1
        s[1] += r['degraded']
        s[2] += r['will_degrade']
        s[3] += r['onset']
    print(f"\n{'EVENT TYPE':<12}{'ROWS':>9}{'DEGRADED':>11}{'WILL_DEGRADE':>14}{'ONSET ROWS':>12}   (protected devices, valid rows)")
    for name in sorted(stats):
        s = stats[name]
        print(f'{name:<12}{s[0]:>9}{pct(s[1], s[0]):>11}{pct(s[2], s[0]):>14}{s[3]:>12}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--session', type=int)
    p.add_argument('--all', action='store_true')
    args = p.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    thresholds = read_thresholds(CONFIG)

    if args.all:
        names = sorted(n for n in os.listdir(IN_DIR) if n.startswith('session_') and n.endswith('.csv'))
    elif args.session is not None:
        names = [f'session_{args.session:03d}.csv']
    else:
        p.error('give --session N or --all')

    everything = []
    cols = None
    for name in names:
        cols, rows = label_session(os.path.join(IN_DIR, name), thresholds)
        with open(os.path.join(OUT_DIR, name), 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=cols + NEW_COLS)
            w.writeheader()
            w.writerows(rows)
        valid = sum(1 for r in rows if r['label_valid'] == 1)
        deg = sum(r['degraded'] for r in rows if r['label_valid'] == 1)
        print(f'{name}: {len(rows)} rows, {valid} valid, degraded {pct(deg, valid)}')
        everything += rows
    if args.all:
        with open(os.path.join(OUT_DIR, 'all_sessions.csv'), 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=cols + NEW_COLS)
            w.writeheader()
            w.writerows(everything)
        print(f'all_sessions.csv: {len(everything)} rows from {len(names)} sessions')
    report(everything)


if __name__ == '__main__':
    main()