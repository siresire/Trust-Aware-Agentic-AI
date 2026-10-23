"""
policy.py - read, check and save the homeowner's rules (models/homeowner_policy.json).
The first save keeps the experiment's rules in models/homeowner_policy.default.json,
so "Reset" always brings back exactly what the paper's runs used.
The agent reads the rules when it starts, so a change is used from the next agent start.
"""
import json
import os
import shutil

from dashboards.web import config

PATH = 'models/homeowner_policy.json'
DEFAULT = 'models/homeowner_policy.default.json'
LEVELS = ['high', 'medium', 'low']
KINDS = ['jam', 'internet_fault', 'device_fault']
LIMITS = {'min_rate_mbit': (1, 10), 'max_slow_s': (20, 300), 'recheck_every_s': (4, 30)}


def read(path=PATH):
    with open(path) as f:
        return json.load(f)


def default():
    return read(DEFAULT) if os.path.exists(DEFAULT) else read(PATH)


def changes(p, d):
    """What differs from the experiment's rules, in words."""
    out = []
    for dev in config.LIMITABLE:
        if (dev in p['may_slow']) != (dev in d['may_slow']):
            out.append(f"the {dev} {'may' if dev in p['may_slow'] else 'may not'} be slowed")
    for dev in config.PROTECTED:
        if p['protected'].get(dev) != d['protected'].get(dev):
            out.append(f"{dev}: {p['protected'].get(dev)} importance (was {d['protected'].get(dev)})")
    names = {'min_rate_mbit': 'slow to', 'max_slow_s': 'undo after', 'recheck_every_s': 'check again after'}
    units = {'min_rate_mbit': ' Mbit/s', 'max_slow_s': ' s', 'recheck_every_s': ' s'}
    for k, name in names.items():
        if p[k] != d[k]:
            out.append(f"{name} {p[k]}{units[k]} (was {d[k]}{units[k]})")
    for k in KINDS:
        if p['tell_homeowner'].get(k) != d['tell_homeowner'].get(k):
            out.append(f"{'tell' if p['tell_homeowner'].get(k) else 'do not tell'} the homeowner about a {k.replace('_', ' ')}")
    return out


def check(new):
    """-> (clean rules, list of problems). Only values the agent can really use are accepted."""
    errors = []
    may = [d for d in new.get('may_slow', []) if d in config.LIMITABLE]
    if len(may) != len(new.get('may_slow', [])):
        errors.append('Only the phone, tv and laptop can be slowed (they are the only devices with a switch port the agent controls).')
    prot = {}
    for dev in config.PROTECTED:
        lv = new.get('protected', {}).get(dev, 'low')
        if lv not in LEVELS:
            errors.append(f'{dev}: importance must be high, medium or low.')
        prot[dev] = lv
    nums = {}
    for k, (lo, hi) in LIMITS.items():
        try:
            v = float(new.get(k))
        except (TypeError, ValueError):
            errors.append(f'{k} must be a number.')
            continue
        if not lo <= v <= hi:
            errors.append(f'{k} must be between {lo} and {hi}.')
        nums[k] = int(v) if v == int(v) else round(v, 1)
    if nums.get('recheck_every_s', 0) >= nums.get('max_slow_s', 1e9):
        errors.append('"Check again after" must be shorter than "Undo after".')
    tell = {k: bool(new.get('tell_homeowner', {}).get(k)) for k in KINDS}
    clean = {'protected': prot, 'may_slow': [d for d in config.LIMITABLE if d in may], **nums, 'tell_homeowner': tell}
    return clean, errors


def _write_like(path, text, like):
    """Write a file, keeping the owner of `like` (the dashboard may run with sudo)."""
    with open(path, 'w') as f:
        f.write(text)
    try:
        st = os.stat(like)
        os.chown(path, st.st_uid, st.st_gid)
    except OSError:
        pass


def _apply(p):
    config.POLICY.clear()
    config.POLICY.update(p)          # the dashboard's own checks use the new rules right away


def save(new):
    clean, errors = check(new)
    if errors:
        return False, errors
    if not os.path.exists(DEFAULT):                       # keep the experiment's rules once
        shutil.copy(PATH, DEFAULT)
        _write_like(DEFAULT, open(DEFAULT).read(), PATH)
    _write_like(PATH, json.dumps(clean, indent=2) + '\n', PATH)
    _apply(clean)
    return True, []


def reset():
    if os.path.exists(DEFAULT):
        _write_like(PATH, open(DEFAULT).read(), PATH)
    _apply(read())
    return True, []


def state():
    p, d = read(), default()
    return {'policy': p, 'default': d, 'changed': changes(p, d), 'limits': LIMITS,
            'used_by_agent': ['may_slow', 'min_rate_mbit', 'max_slow_s', 'recheck_every_s', 'tell_homeowner']}
