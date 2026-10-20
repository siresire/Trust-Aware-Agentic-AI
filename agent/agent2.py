"""
agent2.py - Agent 2, the verifier (the trust check). Every 2 seconds it takes
Agent 1's proposal and decides whether it can be trusted:
  1. checks the shared line (a real jam fills it, a fault does not)
  2. names the problem: jam, internet fault, device fault or ok
  3. waits until the problem is steady (the waiting rules in agent_rules.json)
  4. checks the homeowner rules (homeowner_policy.json)
It still does not act: it prints Agent 1's proposal and its own verdict.

Run from the project root, with the network running:
    python -m agent.agent2
"""
import time
from collections import deque

from agent.agent1 import look, propose, RULES, WARN
from agent.actions import POLICY
from agent.live_features import make_live_folder, build_now, INTERVAL
from ml import label

FULL = RULES['link_full']                          # 0.8: the line counts as full
MIN_NET = RULES['internet_fault_min_devices']      # 3 or more warned = internet fault
WAIT = RULES['wait']                               # how steady each problem must be
ORDER = ['jam', 'internet fault', 'device fault']  # if two are steady, the first wins


def diagnose(snap):
    """Name the problem in ONE snapshot (the same rule as the offline notebook)."""
    if snap['max_prob'] < WARN:
        return 'ok'
    if snap['link'] >= FULL:
        return 'jam'
    if snap['n_alarm'] >= MIN_NET:
        return 'internet fault'
    return 'device fault'


def steady(history):
    """The problem that has lasted long enough, or 'ok'."""
    for kind in ORDER:
        hits, of_last = WAIT[kind]['hits'], WAIT[kind]['of_last']
        recent = list(history)[-of_last:]
        if len(recent) == of_last and recent.count(kind) >= hits:
            return kind
    return 'ok'


def verify(proposal, kind, snap):
    """Agent 2's verdict on Agent 1's proposal."""
    if kind == 'jam':
        dev = proposal['device']
        if proposal['action'] != 'slow':
            return 'REFUSE', 'jam, but Agent 1 proposed nothing'
        if dev not in POLICY['may_slow']:
            return 'REFUSE', f'{dev} is not on the homeowner may_slow list'
        return 'APPROVE', f"slow {dev}: line {snap['link']:.2f} is full"
    if proposal['action'] == 'slow':
        why = 'not steady yet' if kind == 'ok' else kind
        return 'REFUSE', f"line {snap['link']:.2f} is not full ({why})"
    return 'OK', 'nothing to do'


def report(kind, warned):
    """What the homeowner should be told, following the homeowner rules."""
    if kind == 'ok' or not POLICY['tell_homeowner'].get(kind.replace(' ', '_')):
        return ''
    if kind == 'internet fault':
        return 'TELL HOMEOWNER: the internet connection has a problem'
    return f"TELL HOMEOWNER: device problem on {','.join(warned)}"


def main():
    make_live_folder()
    thresholds = label.read_thresholds(label.CONFIG)
    history = deque(maxlen=5)                      # the last 5 one-snapshot names
    last_warned = []                               # devices warned in the last device-fault snapshot
    print(f'Agent 2 running: line full at {FULL}, waiting rules {WAIT}', flush=True)
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
            p = f"{proposal['action']} {proposal['device'] or ''}".strip()
            print(f"{time.strftime('%H:%M:%S')}  prob {snap['max_prob']:4.2f}  "
                  f"alarms {snap['n_alarm']}  link {snap['link']:4.2f}  "
                  f"now {history[-1]:14s} steady {kind:14s}  "
                  f"A1: {p:11s}  A2: {verdict:7s} {why}  {report(kind, last_warned)}", flush=True)
        time.sleep(max(0, INTERVAL - (time.time() - t)))


if __name__ == '__main__':
    main()