"""

    python3 -m ml.split
"""
import csv
import json
import os
import random

FEATURE_DIR = 'data/features'
OUT_FILE = 'data/splits.json'

TRAIN_SESSIONS = list(range(1, 41))        # used to build and tune the model
TEST_SESSIONS = list(range(41, 65))        # never looked at until the final test
BASELINE_SESSIONS = [101, 102, 103]        # the thresholds came from these
NORMAL_TEST_SESSIONS = [105, 106, 107, 108, 109, 110]   # false-alarm test
EXCLUDED = {104: 'machine was busy for about five minutes during recording'}

N_FOLDS = 5
FOLD_SEED = 42


def make_folds(sessions, n_folds, seed):
    """Shuffle the sessions once, then deal them into n_folds groups."""
    shuffled = sessions[:]
    random.Random(seed).shuffle(shuffled)
    return [sorted(shuffled[i::n_folds]) for i in range(n_folds)]


def count_session(session):
    """Valid rows, positive rows and events of one session."""
    path = os.path.join(FEATURE_DIR, f'session_{session:03d}.csv')
    if not os.path.exists(path):
        return None
    rows = pos = onset = 0
    events = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            if r['label_valid'] != '1':
                continue
            rows += 1
            pos += int(r['will_degrade'])
            onset += int(r['onset'])
            if r['event_id']:
                events[r['event_id']] = r['event_type']
    by_type = {}
    for t in events.values():
        by_type[t] = by_type.get(t, 0) + 1
    return {'rows': rows, 'pos': pos, 'onset': onset, 'events': by_type}


def summarise(name, sessions):
    total = {'rows': 0, 'pos': 0, 'onset': 0}
    events = {}
    found = 0
    for s in sessions:
        c = count_session(s)
        if c is None:
            continue
        found += 1
        for k in total:
            total[k] += c[k]
        for t, n in c['events'].items():
            events[t] = events.get(t, 0) + n
    share = 100.0 * total['pos'] / total['rows'] if total['rows'] else 0.0
    ev = ', '.join(f'{t} {n}' for t, n in sorted(events.items())) or 'no events'
    print(f"{name:<14}{found:>3} sessions {total['rows']:>8} rows  will_degrade {share:5.1f} %  "
          f"onset {total['onset']:>6}   {ev}")


def main():
    folds = make_folds(TRAIN_SESSIONS, N_FOLDS, FOLD_SEED)
    splits = {
        'rule': 'split by whole session; rows with label_valid = 0 are dropped',
        'train': TRAIN_SESSIONS,
        'folds': folds,
        'test': TEST_SESSIONS,
        'normal_test': NORMAL_TEST_SESSIONS,
        'baseline': BASELINE_SESSIONS,
        'excluded': {str(k): v for k, v in EXCLUDED.items()},
        'fold_seed': FOLD_SEED,
    }
    with open(OUT_FILE, 'w') as f:
        json.dump(splits, f, indent=2)
    print(f'written {OUT_FILE}\n')

    summarise('train (1-40)', TRAIN_SESSIONS)
    for i, fold in enumerate(folds, 1):
        summarise(f'  fold {i}', fold)
    summarise('test (41-64)', TEST_SESSIONS)
    summarise('normal test', NORMAL_TEST_SESSIONS)

    used = set(TRAIN_SESSIONS) | set(TEST_SESSIONS) | set(NORMAL_TEST_SESSIONS) | set(BASELINE_SESSIONS) | set(EXCLUDED)
    overlap = set(TRAIN_SESSIONS) & (set(TEST_SESSIONS) | set(NORMAL_TEST_SESSIONS))
    on_disk = {int(n[8:11]) for n in os.listdir(FEATURE_DIR) if n.startswith('session_')}
    print(f'\nsessions in both train and test: {len(overlap)}')
    print(f'sessions on disk not assigned anywhere: {sorted(on_disk - used)}')


if __name__ == '__main__':
    main()