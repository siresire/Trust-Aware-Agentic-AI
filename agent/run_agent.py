"""
run_agent.py - the two agents acting on the live network.
Every 2 seconds Agent 1 proposes and Agent 2 verifies. Then the actor:
  - slows a device when Agent 2 approves (actions.slow_down)
  - checks 10 s later whether it helped; if the jam is still there, slows the next sender
  - undoes every slow-down after max_slow_s (60 s)
  - undoes everything when it stops (Ctrl+C)
Every tick and every action is written to data/live/agent_log.jsonl.

Three modes, for the experiment (same code, only who decides changes):
    --mode trust     Agent 1 proposes, Agent 2 checks, then act   (trust-aware, the default)
    --mode predict   act on every Agent 1 proposal, no check       (prediction-only)
    --mode none      never act, only watch and log                 (no agent)

Needs root (ovs-vsctl). Run from the project root, with the network running:
    sudo .venv/bin/python -m agent.run_agent --mode trust
"""
import argparse
import json
import os
import time
from collections import deque

from agent.agent1 import look, propose
from agent.agent2 import diagnose, steady, verify, report, FULL
from agent.actions import POLICY, PORTS, slow_down, undo
from agent.live_features import make_live_folder, build_now, INTERVAL
from ml import label

LOG = 'data/live/agent_log.jsonl'
RATE = POLICY['min_rate_mbit']          # slow to the lowest speed the homeowner allows (2)
RECHECK = POLICY['recheck_every_s']     # check 10 s after acting
MAX_SLOW = POLICY['max_slow_s']         # undo after 60 s
THRESHOLDS = 'config_ubuntu.yaml'       # this host's normal delays (config.yaml = Kali, used for training)
MODES = ['trust', 'predict', 'none']


class Actor:
    """Does the slowing and undoing, and remembers what it did and when."""

    def __init__(self, log):
        self.log = log
        self.slowed = {}                # device -> time it was slowed
        self.last_act = 0.0             # time of the last slow-down
        self.link_at_act = None         # how full the line was when we acted
        self.check_due = False          # a check after acting is still to do

    def note(self, what, **info):
        """Write one action line to the log and the screen."""
        self.log.write(json.dumps({'t': round(time.time(), 2), 'event': what, **info}) + '\n')
        self.log.flush()
        print(f"          >>> {what}  {info}", flush=True)

    def slow_next(self, snap):
        """Slow the biggest sender that is not slowed yet."""
        free = [d for d in snap['senders'] if d not in self.slowed]
        if not free:
            self.note('NOTHING LEFT TO SLOW', slowed=list(self.slowed))
            return
        ok, msg = slow_down(free[0], RATE)
        self.note('SLOW' if ok else 'SLOW REFUSED', device=free[0], msg=msg)
        if ok:
            self.slowed[free[0]] = time.time()
            self.last_act = time.time()
            self.link_at_act = round(float(snap['link']), 2)
            self.check_due = True

    def undo_one(self, device, reason):
        ok, msg = undo(device)
        self.note('UNDO', device=device, reason=reason,
                  after_s=round(time.time() - self.slowed.pop(device)), msg=msg)

    def step(self, verdict, kind, snap):
        """Called every tick, after Agent 2's verdict."""
        t = time.time()
        # 1. never keep a device slow for longer than the homeowner allows
        for dev, since in list(self.slowed.items()):
            if t - since >= MAX_SLOW:
                self.undo_one(dev, f'{MAX_SLOW} s limit')
        # 2. check after acting: did the jam go away?
        if self.check_due and t - self.last_act >= RECHECK:
            self.check_due = False
            helped = kind != 'jam'
            self.note('CHECK', helped=helped, problem_now=kind,
                      link_before=self.link_at_act, link_now=round(float(snap['link']), 2))
            if not helped:
                self.slow_next(snap)
            return
        # 3. a new approved jam (only when we are not waiting for a check)
        if verdict == 'APPROVE' and not self.check_due and len(self.slowed) < len(snap['senders']):
            self.slow_next(snap)

    def undo_all(self, reason):
        for dev in list(self.slowed):
            self.undo_one(dev, reason)


def decide(mode, proposal, verdict, kind):
    """What the actor is told to do, depending on the mode."""
    if mode == 'trust':                              # Agent 2 decides
        return verdict, kind
    if mode == 'predict':                            # Agent 1 alone: every warning is treated as a jam
        if proposal['action'] == 'slow':
            return 'APPROVE', 'jam'
        return 'OK', 'ok'
    return 'OK', kind                                # none: never act


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=MODES, default='trust')
    p.add_argument('--log', default=LOG, help='where to write the log')
    args = p.parse_args()

    make_live_folder()
    thresholds = label.read_thresholds(THRESHOLDS)
    print(f'normal delays from {THRESHOLDS}', flush=True)
    os.makedirs(os.path.dirname(args.log), exist_ok=True)
    log = open(args.log, 'w')                       # a fresh log for every run
    log.write(json.dumps({'t': round(time.time(), 2), 'event': 'START', 'mode': args.mode,
                          'thresholds': THRESHOLDS}) + '\n')
    for dev in PORTS:                               # start clean: no old limits left
        undo(dev)
    actor = Actor(log)
    history = deque(maxlen=5)
    last_warned = []
    print(f'MODE {args.mode}: line full at {FULL}, slow to {RATE} Mbit/s, '
          f'check after {RECHECK} s, undo after {MAX_SLOW} s', flush=True)
    try:
        while True:
            t = time.time()
            now = build_now(thresholds)
            if now is None:
                print('no live logs yet - is the network running?', flush=True)
            else:
                snap = look(now)
                proposal = propose(snap)
                history.append(diagnose(snap))
                if history[-1] == 'device fault':
                    last_warned = snap['warned']
                kind = steady(history)
                verdict, why = verify(proposal, kind, snap)
                tell = report(kind, last_warned)
                p = f"{proposal['action']} {proposal['device'] or ''}".strip()
                print(f"{time.strftime('%H:%M:%S')}  prob {snap['max_prob']:4.2f}  "
                      f"alarms {snap['n_alarm']}  link {snap['link']:4.2f}  "
                      f"steady {kind:14s}  A1: {p:11s}  A2: {verdict:7s}  "
                      f"slowed: {','.join(actor.slowed) or '-':18s} {tell}", flush=True)
                log.write(json.dumps({
                    't': round(time.time(), 2), 'event': 'TICK',
                    'prob': round(float(snap['max_prob']), 3), 'alarms': snap['n_alarm'],
                    'warned': snap['warned'], 'link': round(float(snap['link']), 3),
                    'top': snap['top_sender'], 'now': history[-1], 'steady': kind,
                    'a1': p, 'a2': verdict, 'why': why, 'tell': tell,
                    'slowed': list(actor.slowed)}) + '\n')
                actor.step(*decide(args.mode, proposal, verdict, kind), snap)
            time.sleep(max(0, INTERVAL - (time.time() - t)))
    except KeyboardInterrupt:
        print('\nstopping', flush=True)
    finally:
        actor.undo_all('agent stopped')
        log.close()


if __name__ == '__main__':
    main()