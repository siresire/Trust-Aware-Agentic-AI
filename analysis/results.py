"""
results.py - the experiment's tables and figures.
Reads the 9 runs (3 seeds x 3 modes) and the answer sheet of each session, and writes
everything the paper needs into results/.

    data/experiment/agent_<session>_<mode>.jsonl   what the agent saw and did every 2 s
    data/raw/session_<session>/events.csv          when each event started and ended (the truth)
    data/raw/session_<session>/network_metrics/    how every device actually felt

Run from the project root (no sudo):
    .venv/bin/python -m analysis.results
"""
import csv
import glob
import json
import os
import statistics
from collections import Counter

import matplotlib
matplotlib.use('Agg')                       # write files, no window
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from ml import label

EXP_DIR = 'data/experiment'
RAW_DIR = 'data/raw'
OUT_DIR = 'results'
THRESHOLDS = 'config_ubuntu.yaml'           # the same normal levels the live agent used

MODES = ['none', 'predict', 'trust']
NAME = {'none': 'No agent', 'predict': 'Prediction-only', 'trust': 'Trust-aware'}
JAMS = ('C_SEVERE', 'C_BORDER')
FAULTS = ('F_WAN', 'F_DEVLINK')
RIGHT_NAME = {'C_SEVERE': 'jam', 'C_BORDER': 'jam',
              'F_WAN': 'internet fault', 'F_DEVLINK': 'device fault'}
PROTECTED = ['camera', 'doorbell', 'lock', 'thermostat', 'speaker', 'light', 'plug']

GRACE_S = 10        # an action this soon after an event ends still belongs to that event
RECOVERY_S = 30     # after an event, this long is the event's tail, not calm time

# black-and-white print: each mode has its own fill pattern, not a colour
STYLE = {'none':    dict(color='white', edgecolor='black', hatch=''),
         'predict': dict(color='white', edgecolor='black', hatch='///'),
         'trust':   dict(color='0.25', edgecolor='black', hatch='')}


# ---------------------------------------------------------------- reading the files

def read_events(session_dir):
    """events.csv -> one dict per event: type, devices, start, end."""
    events = {}
    with open(os.path.join(session_dir, 'events.csv')) as f:
        for r in csv.DictReader(f):
            key = r.get('schedule_id') or r['event_id']
            ev = events.setdefault(key, {'id': key, 'type': r['event_type'], 'devices': set(),
                                         'start': None, 'end': None})
            ev['devices'].add(r['device'])
            t = float(r['timestamp'])
            if r['phase'] == 'start':
                ev['start'] = t if ev['start'] is None else min(ev['start'], t)
            elif r['phase'] == 'end':
                ev['end'] = t if ev['end'] is None else max(ev['end'], t)
    return sorted((e for e in events.values() if e['start'] and e['end']), key=lambda e: e['start'])


def read_agent(path):
    """One agent log -> mode, ticks, actions."""
    mode, ticks, actions = None, [], []
    with open(path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue                                 # a half-written last line
            if r['event'] == 'START':
                mode = r['mode']
            elif r['event'] == 'TICK':
                ticks.append(r)
            else:
                actions.append(r)
    return mode, ticks, actions


def slowed_spans(actions, t_end):
    """(device, from, to) for every slow-down; one never undone lasts until t_end."""
    open_, spans = {}, []
    for a in actions:
        if a['event'] == 'SLOW':
            open_[a['device']] = a['t']
        elif a['event'] == 'UNDO' and a['device'] in open_:
            spans.append((a['device'], open_.pop(a['device']), a['t']))
    spans += [(d, t0, t_end) for d, t0 in open_.items()]
    return spans


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def read_readings(session_dir, thr):
    """Every protected-device reading: (time, rtt or None, bad)."""
    out = []
    for dev in PROTECTED:
        path = os.path.join(session_dir, 'network_metrics', dev + '.log')
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for r in csv.DictReader(f):
                try:
                    t = float(r['timestamp'])
                except (TypeError, ValueError):
                    continue
                rtt = label_num(r['rtt_ms'])
                loss = label_num(r['loss_pct']) or 0.0
                bad = rtt is None or loss > 0 or rtt > thr[dev]
                out.append((t, rtt, bad))
    return out


def label_num(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- one run

def score_run(path, thr):
    """Everything we measure in one run (one session in one mode)."""
    mode, ticks, actions = read_agent(path)
    session = int(os.path.basename(path).split('_')[1])
    session_dir = os.path.join(RAW_DIR, f'session_{session:03d}')
    with open(os.path.join(session_dir, 'meta.json')) as f:
        seed = json.load(f)['seed']
    events = read_events(session_dir)
    t0, t1 = ticks[0]['t'], ticks[-1]['t']                     # when the agent was watching
    events = [e for e in events if e['start'] >= t0 and e['end'] <= t1]
    slows = [a for a in actions if a['event'] == 'SLOW']
    spans = slowed_spans(actions, t1)
    readings = read_readings(session_dir, thr)

    rows = []
    for e in events:
        win0, win1 = e['start'], e['end'] + GRACE_S
        mine = [a for a in slows if win0 <= a['t'] <= win1]
        during = [r for r in ticks if e['start'] <= r['t'] <= e['end']]
        named = Counter(r['steady'] for r in during if r['steady'] != 'ok')
        prot = [r for r in readings if e['start'] <= r[0] <= e['end']]
        rtts = [r[1] for r in prot if r[1] is not None]
        rows.append({
            'session': session, 'seed': seed, 'mode': mode,
            'event': e['id'], 'type': e['type'], 'devices': '|'.join(sorted(e['devices'])),
            'duration_s': round(e['end'] - e['start'], 1),
            'slowdowns': len(mine),
            'first_slow_s': round(mine[0]['t'] - e['start'], 1) if mine else '',
            'slowed_flooder': sum(a['device'] in e['devices'] for a in mine),
            'slowed_seconds': round(sum(overlap(a, b, e['start'], e['end']) for _, a, b in spans), 1),
            'named_as': named.most_common(1)[0][0] if named else 'ok',
            'name_right': int(bool(named) and named.most_common(1)[0][0] == RIGHT_NAME[e['type']]),
            'protected_bad_pct': round(100 * sum(r[2] for r in prot) / len(prot), 1) if prot else '',
            'protected_rtt_median': round(statistics.median(rtts), 1) if rtts else '',
        })

    # calm time: no event running, and not in the 30 s after one
    busy = [(e['start'], e['end'] + RECOVERY_S) for e in read_events(session_dir)]
    def calm(t):
        return t0 <= t <= t1 and not any(a <= t <= b for a, b in busy)
    calm_ticks = [r for r in ticks if calm(r['t'])]
    new_msgs = sum(1 for i, r in enumerate(ticks)
                   if r['tell'] and calm(r['t']) and (i == 0 or ticks[i - 1]['tell'] != r['tell']))
    run = {
        'session': session, 'seed': seed, 'mode': mode,
        'calm_hours': len(calm_ticks) * 2 / 3600,
        'calm_slowdowns': sum(1 for a in slows if calm(a['t'])),
        'calm_messages': new_msgs,
        'all_slowdowns': len(slows),
    }
    return run, rows, ticks, spans, events


# ---------------------------------------------------------------- the tables

def pct(part, whole):
    return f'{100 * part / whole:.0f}%' if whole else '-'


def med(values):
    return f'{statistics.median(values):.1f}' if values else '-'


def table_main(runs, rows):
    """Table 1: what each policy did."""
    out = ['| | ' + ' | '.join(NAME[m] for m in MODES) + ' |', '|---|' + '---|' * len(MODES)]
    def line(title, fn):
        out.append(f'| {title} | ' + ' | '.join(fn(m) for m in MODES) + ' |')
    J = {m: [r for r in rows if r['mode'] == m and r['type'] in JAMS] for m in MODES}
    F = {m: [r for r in rows if r['mode'] == m and r['type'] in FAULTS] for m in MODES}
    R = {m: [r for r in runs if r['mode'] == m] for m in MODES}
    line('Jams (events)', lambda m: str(len(J[m])))
    line('Jams acted on', lambda m: pct(sum(r['slowdowns'] > 0 for r in J[m]), len(J[m])))
    line('Time to first slow-down (median, s)',
         lambda m: med([r['first_slow_s'] for r in J[m] if r['first_slow_s'] != '']))
    line('Slow-downs during jams that hit a flooder',
         lambda m: pct(sum(r['slowed_flooder'] for r in J[m]), sum(r['slowdowns'] for r in J[m])))
    line('Faults (events)', lambda m: str(len(F[m])))
    line('Faults with a wrong slow-down',
         lambda m: pct(sum(r['slowdowns'] > 0 for r in F[m]), len(F[m])))
    line('Device-seconds slowed during faults',
         lambda m: f"{sum(r['slowed_seconds'] for r in F[m]):.0f}")
    line('Calm time (hours)', lambda m: f"{sum(r['calm_hours'] for r in R[m]):.2f}")
    line('Slow-downs in calm time (per hour)',
         lambda m: f"{sum(r['calm_slowdowns'] for r in R[m]) / max(1e-9, sum(r['calm_hours'] for r in R[m])):.1f}")
    return '\n'.join(out)


def table_protected(rows):
    """Table 2: how the protected devices felt during the events."""
    out = ['| Event type | ' + ' | '.join(NAME[m] for m in MODES) + ' |', '|---|' + '---|' * len(MODES)]
    for t in JAMS + FAULTS:
        cells = []
        for m in MODES:
            these = [r for r in rows if r['mode'] == m and r['type'] == t and r['protected_bad_pct'] != '']
            cells.append(f"{statistics.mean(r['protected_bad_pct'] for r in these):.0f}% bad"
                         if these else '-')
        out.append(f'| {t} | ' + ' | '.join(cells) + ' |')
    return '\n'.join(out)


def table_diagnosis(runs, rows):
    """Table 3: did the trust-aware agent name each event right, and how often did it bother the homeowner."""
    T = [r for r in rows if r['mode'] == 'trust']
    out = ['| Event type | Events | Named right | Named as (count) |', '|---|---|---|---|']
    for t in JAMS + FAULTS:
        these = [r for r in T if r['type'] == t]
        names = Counter(r['named_as'] for r in these)
        out.append(f'| {t} | {len(these)} | {pct(sum(r["name_right"] for r in these), len(these))} | '
                   + ', '.join(f'{k} {v}' for k, v in names.most_common()) + ' |')
    R = [r for r in runs if r['mode'] == 'trust']
    hours = sum(r['calm_hours'] for r in R)
    msgs = sum(r['calm_messages'] for r in R)
    out.append('')
    out.append(f'Homeowner messages in calm time: {msgs} in {hours:.2f} h '
               f'({msgs / max(1e-9, hours):.1f} per hour)')
    return '\n'.join(out)


# ---------------------------------------------------------------- the figures

def bar_figure(path, title, ylabel, values):
    """One bar per mode, black and white, the value written on each bar."""
    fig, ax = plt.subplots(figsize=(4.2, 3.0))
    xs = range(len(MODES))
    for x, m in zip(xs, MODES):
        ax.bar(x, values[m], width=0.6, linewidth=1, **STYLE[m])
        ax.text(x, values[m] + 1.5, f'{values[m]:.0f}%', ha='center', va='bottom', fontsize=9)
    ax.set_xticks(list(xs), [NAME[m] for m in MODES], fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_ylim(0, 105)
    ax.set_title(title, fontsize=10)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    ax.yaxis.grid(True, color='0.85', linewidth=0.6)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path + '.png', dpi=300)
    fig.savefig(path + '.pdf')
    plt.close(fig)


def timeline_figure(path, seed, by_mode):
    """One session, three panels: the shared line, and when each policy slowed a device."""
    fig, axes = plt.subplots(3, 1, figsize=(7.0, 4.4), sharex=True,
                             gridspec_kw={'height_ratios': [2.2, 1, 1]})
    ticks, events = by_mode['none']['ticks'], by_mode['none']['events']
    start = ticks[0]['t']
    mins = lambda t: (t - start) / 60
    for ax in axes:
        for e in events:                                   # events: jams dark, faults hatched
            if e['type'] in JAMS:
                ax.axvspan(mins(e['start']), mins(e['end']), color='0.75', linewidth=0)
            else:
                ax.axvspan(mins(e['start']), mins(e['end']), facecolor='white',
                           edgecolor='0.55', hatch='\\\\', linewidth=0)
    axes[0].plot([mins(r['t']) for r in ticks], [r['link'] for r in ticks], color='black', linewidth=0.8)
    axes[0].axhline(0.8, color='black', linestyle='--', linewidth=0.8)
    axes[0].text(mins(ticks[-1]['t']), 0.82, 'line full (0.8)', ha='right', va='bottom', fontsize=7,
                 bbox=dict(facecolor='white', edgecolor='none', pad=1))
    axes[0].set_ylabel('Shared line\n(no agent)', fontsize=8)
    axes[0].set_ylim(0, 1.05)
    devices = ['phone', 'tv', 'laptop']
    for ax, m in zip(axes[1:], ['predict', 'trust']):
        for dev, a, b in by_mode[m]['spans']:
            ax.plot([mins(a), mins(b)], [devices.index(dev)] * 2, color='black', linewidth=4,
                    solid_capstyle='butt')
        ax.set_yticks(range(3), devices, fontsize=7)
        ax.set_ylim(-0.7, 2.7)
        ax.set_ylabel(f'{NAME[m]}\nslowed', fontsize=8)
    axes[-1].set_xlabel('Minutes into the session', fontsize=8)
    for ax in axes:
        ax.tick_params(labelsize=7)
        for side in ('top', 'right'):
            ax.spines[side].set_visible(False)
    jam = Patch(color='0.75', label='jam')
    fault = Patch(facecolor='white', edgecolor='0.55', hatch='\\\\', label='fault')
    axes[0].legend(handles=[jam, fault], loc='upper left', fontsize=7, frameon=False, ncol=2)
    axes[0].set_title(f'Session with seed {seed}: the same events under each policy', fontsize=9)
    fig.tight_layout()
    fig.savefig(path + '.png', dpi=300)
    fig.savefig(path + '.pdf')
    plt.close(fig)


# ---------------------------------------------------------------- main

def write_csv(path, rows):
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    thr = label.read_thresholds(THRESHOLDS)
    runs, rows, per_seed = [], [], {}
    for path in sorted(glob.glob(os.path.join(EXP_DIR, 'agent_*.jsonl'))):
        run, run_rows, ticks, spans, events = score_run(path, thr)
        runs.append(run)
        rows += run_rows
        per_seed.setdefault(run['seed'], {})[run['mode']] = dict(ticks=ticks, spans=spans, events=events)
        print(f"read session {run['session']} (seed {run['seed']}, {run['mode']}): "
              f"{len(run_rows)} events, {run['all_slowdowns']} slow-downs")

    write_csv(os.path.join(OUT_DIR, 'events_scored.csv'), rows)
    write_csv(os.path.join(OUT_DIR, 'runs_scored.csv'), runs)

    text = ['# Results', '',
            '## Table 1: what each policy did (all three sessions together)', '', table_main(runs, rows), '',
            '## Table 2: protected devices during events (share of readings that were bad)', '',
            table_protected(rows), '',
            '## Table 3: the trust-aware agent\'s diagnosis', '', table_diagnosis(runs, rows), '']
    with open(os.path.join(OUT_DIR, 'results.md'), 'w') as f:
        f.write('\n'.join(text))
    print('\n'.join(text))

    F = {m: [r for r in rows if r['mode'] == m and r['type'] in FAULTS] for m in MODES}
    bar_figure(os.path.join(OUT_DIR, 'fig_wrong_slowdowns'),
               'Faults with a wrong slow-down', '% of fault events',
               {m: 100 * sum(r['slowdowns'] > 0 for r in F[m]) / max(1, len(F[m])) for m in MODES})
    J = {m: [r for r in rows if r['mode'] == m and r['type'] in JAMS and r['protected_bad_pct'] != '']
         for m in MODES}
    bar_figure(os.path.join(OUT_DIR, 'fig_protected_during_jams'),
               'Protected devices during jams', '% of readings that were bad',
               {m: statistics.mean(r['protected_bad_pct'] for r in J[m]) if J[m] else 0 for m in MODES})
    for seed, by_mode in sorted(per_seed.items()):
        if all(m in by_mode for m in MODES):
            timeline_figure(os.path.join(OUT_DIR, f'fig_timeline_seed{seed}'), seed, by_mode)
    print(f'\nTables: {OUT_DIR}/results.md   Figures: {OUT_DIR}/fig_*.png and .pdf')


if __name__ == '__main__':
    main()