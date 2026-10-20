"""
agent1.py - Agent 1, the predictor. Every 2 seconds it builds the live features,
scores every protected device with the saved model, and PROPOSES an action.
It never acts and never checks the network itself: that is Agent 2's job.

Run from the project root, with the network running:
    python -m agent.agent1
"""
import json
import time
import warnings

import joblib

from agent.live_features import make_live_folder, build_now, INTERVAL
from ml import label

warnings.filterwarnings('ignore', category=UserWarning)   # feature-name notes from sklearn

BUNDLE = joblib.load('models/degrade_model_v1.joblib')
RULES = json.load(open('models/agent_rules.json'))
MODEL, FIXER, FEATURES = BUNDLE['model'], BUNDLE['fixer'], BUNDLE['features']
WARN = RULES['warn_prob']                                  # 0.5


def score(now):
    """Honest probability of trouble for each protected device."""
    prot = now[now['is_protected'] == 1].copy()
    raw = MODEL.predict_proba(prot[FEATURES])[:, 1]        # the model's own score
    prot['prob'] = FIXER.predict(raw)                      # made honest by the fixer
    return prot


def look(now):
    """One snapshot of the house: the same four things the offline notebook used."""
    prot = score(now)
    lim = now[now['is_protected'] == 0]                    # phone, tv, laptop
    return {
        'max_prob': prot['prob'].max(),
        'n_alarm': int((prot['prob'] >= WARN).sum()),
        'warned': list(prot.index[prot['prob'] >= WARN]),
        'link': now['uplink_util'].max(),
        'top_sender': lim['tx_kbps'].idxmax(),
    }


def propose(snap):
    """Agent 1 trusts its model: any warning -> slow the top sender."""
    if snap['max_prob'] >= WARN:
        return {'action': 'slow', 'device': snap['top_sender'],
                'why': f"{snap['n_alarm']} protected device(s) warned, top prob {snap['max_prob']:.2f}"}
    return {'action': 'none', 'device': None, 'why': 'no warning'}


def main():
    make_live_folder()
    thresholds = label.read_thresholds(label.CONFIG)
    print(f"Agent 1 running: model trained on {len(BUNDLE['trained_on'])} sessions, warns at {WARN}",
          flush=True)
    while True:
        t = time.time()
        now = build_now(thresholds)
        if now is None:
            print('no live logs yet - is the network running?', flush=True)
        else:
            snap = look(now)
            p = propose(snap)
            print(f"{time.strftime('%H:%M:%S')}  prob {snap['max_prob']:4.2f}  "
                  f"alarms {snap['n_alarm']}  link {snap['link']:4.2f}  "
                  f"top {snap['top_sender']:6s}  ->  PROPOSE {p['action']:4s} {p['device'] or '':6s}  "
                  f"{','.join(snap['warned'])}", flush=True)
        time.sleep(max(0, INTERVAL - (time.time() - t)))


if __name__ == '__main__':
    main()