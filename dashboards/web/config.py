"""
config.py - every path and number the dashboard uses, in one place.
The agent's own numbers are read from models/ so the page always matches the agent.
"""
import json

from ml import label

# live logs (written by topo/ and by agent/run_agent.py)
METRICS_DIR = '/tmp/network_metrics'
TCP_DIR = '/tmp/tcp_metrics'
TRAFFIC_LOG = '/tmp/normal_traffic.log'
EVENTS_LOG = '/tmp/events.log'                # start/end of every congest / fault command
AGENT_LOG = 'data/live/agent_log.jsonl'
AGENT_OUT = 'data/live/agent_run.out'         # screen output of an agent started from the page
THRESHOLDS_FILE = 'config_ubuntu.yaml'        # this host's normal delay per device

# recorded runs (replay, comparison, model page)
EXP_DIR = 'data/experiment2'                  # agent_<session>_<mode>.jsonl
RAW_DIR = 'data/raw'                          # session_<session>/ network_metrics, events.csv, meta.json
RESULTS_DIR = 'results'                       # events_scored.csv, runs_scored.csv (analysis/results.py)
NOTEBOOK = 'analysis/29_train_model.ipynb'    # the training notebook (offline scores)

POLICY = json.load(open('models/homeowner_policy.json'))
RULES = json.load(open('models/agent_rules.json'))

INTERVAL = 2                    # network_monitor.py writes one sample every 2 s
STALE_AFTER = 4 * INTERVAL      # no new sample for 8 s = stale
LINK_KBPS = 10000               # bw=10 on every link
LINK_FULL = RULES['link_full']                       # 0.8
WARN_PROB = RULES['warn_prob']                       # 0.5
FAULT_MIN = RULES['internet_fault_min_devices']      # 3
WATCH = 'camera'                # the protected device the page follows most closely

PROTECTED = ['camera', 'doorbell', 'lock', 'thermostat', 'speaker', 'light', 'plug']
LIMITABLE = ['phone', 'tv', 'laptop']
DEVICES = PROTECTED + LIMITABLE
TYPES = {'thermostat': 'Sensor', 'lock': 'Security', 'doorbell': 'Security', 'light': 'Actuator',
         'plug': 'Actuator', 'camera': 'Video', 'speaker': 'Media', 'phone': 'Client',
         'laptop': 'Client', 'tv': 'Media'}
MODES = ['none', 'predict', 'trust']

NORMAL_MS = label.read_thresholds(THRESHOLDS_FILE)   # e.g. {'camera': 119.5, ...}


def for_page():
    """The settings the page needs (sent once, at /api/config)."""
    return {'devices': DEVICES, 'types': TYPES, 'protected': PROTECTED, 'limitable': LIMITABLE,
            'interval': INTERVAL, 'stale_after': STALE_AFTER, 'link_kbps': LINK_KBPS,
            'link_full': LINK_FULL, 'warn_prob': WARN_PROB, 'fault_min': FAULT_MIN,
            'normal_ms': NORMAL_MS, 'watch': WATCH, 'policy': POLICY, 'wait': RULES['wait']}
