"""
scenarios.py - a random but reproducible schedule of labelled events for one session.
Used by run_experiment.py.  Try it:  python3 -m experiments.scenarios --seed 1
"""

import argparse
import random
from collections import Counter

import topo                                    # adds topo/ to the import path (topo/__init__.py)
from congestion import ALLOWED_FLOODERS        # laptop, phone, tv
from faults import FAULT_DEVICES               # camera, doorbell, lock, thermostat, speaker

EVENT_TYPES = {'C_SEVERE': 0.35, 'C_BORDER': 0.25, 'F_WAN': 0.20, 'F_DEVLINK': 0.20}
QUIET_START_S = 120                            # normal traffic only at the start
GAP_S = (45, 120)                              # recovery time after each event
DURATION_S = (15, 60)                          # length of each event


def draw_params(event_type, rng):
    """Pick the parameters for one event of this type."""
    if event_type == 'C_SEVERE':
        return dict(flooders=rng.sample(ALLOWED_FLOODERS, rng.randint(2, 3)),
                    rate_mbps=rng.randint(8, 20))
    if event_type == 'C_BORDER':
        return dict(flooders=[rng.choice(ALLOWED_FLOODERS)],
                    rate_mbps=rng.randint(6, 12))
    if event_type == 'F_WAN':                  # calibrated in the pilot: visible but link not full
        return dict(delay_ms=rng.randint(60, 150), loss_pct=rng.randint(3, 10))
    if event_type == 'F_DEVLINK':              # calibrated in the pilot: clear loss on one device
        return dict(device=rng.choice(FAULT_DEVICES), loss_pct=rng.randint(10, 30))
    raise ValueError(f'unknown event type {event_type}')


def make_schedule(duration_s, n_events, seed):
    """Return up to n_events events that fit in duration_s, each followed by a quiet gap."""
    rng = random.Random(seed)
    types = list(EVENT_TYPES)
    weights = list(EVENT_TYPES.values())

    schedule = []
    t = QUIET_START_S
    for i in range(n_events):
        duration = rng.randint(*DURATION_S)
        gap = rng.randint(*GAP_S)
        if t + duration + gap > duration_s:
            break                                   # no room left for this event + recovery
        event_type = rng.choices(types, weights)[0]
        schedule.append(dict(id=i + 1, type=event_type, t_start=t, duration=duration,
                             params=draw_params(event_type, rng)))
        t += duration + gap
    return schedule


def should_act(event):
    """True only if rate-limiting an allowed device can fix this event."""
    return event['type'].startswith('C_')


def main():
    ap = argparse.ArgumentParser(description='Print an event schedule for one session')
    ap.add_argument('--duration', type=int, default=1800, help='session length in s')
    ap.add_argument('--events', type=int, default=12, help='maximum number of events')
    ap.add_argument('--seed', type=int, default=1)
    args = ap.parse_args()

    schedule = make_schedule(args.duration, args.events, args.seed)
    print(f"{'id':>3}  {'type':<10}{'t_start':>8}{'dur':>5}  {'should_act':<11}params")
    for ev in schedule:
        print(f"{ev['id']:>3}  {ev['type']:<10}{ev['t_start']:>8}{ev['duration']:>5}  "
              f"{str(should_act(ev)):<11}{ev['params']}")

    counts = Counter(ev['type'] for ev in schedule)
    end = schedule[-1]['t_start'] + schedule[-1]['duration'] if schedule else 0
    print(f"\n{len(schedule)} events {dict(counts)}; last event ends at {end} s "
          f"of {args.duration} s")


if __name__ == '__main__':
    main()