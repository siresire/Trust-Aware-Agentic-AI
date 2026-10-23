"""
insights.py - what the page explains, worked out from the logs:
  trust_check()   the trust check on one agent snapshot, step by step (the same rules as agent/agent2.py)
  decisions()     the audit trail: every slow-down and every refusal, with the camera before and after
  compare()       no agent vs prediction-only vs trust-aware, from the recorded experiment
  model_report()  threshold sweep and calibration of Agent 1, measured on the recorded no-agent runs
Nothing here changes a file.
"""
import bisect
import csv
import json
import os
import statistics
from collections import Counter

from dashboards.web import config, logs, sources

POLICY, RULES = config.POLICY, config.RULES
WAIT = RULES['wait']
JAMS, FAULTS = ('C_SEVERE', 'C_BORDER'), ('F_WAN', 'F_DEVLINK')
RIGHT_NAME = {'C_SEVERE': 'jam', 'C_BORDER': 'jam', 'F_WAN': 'internet fault', 'F_DEVLINK': 'device fault'}
GRACE_S = 10          # same as analysis/results.py
RECOVERY_S = 30       # same as analysis/results.py
BEFORE_S = (-6, 0)    # camera window just before an action
AFTER_S = (10, 20)    # camera window after an action (after the 10-second check: the queue needs time to drain)
HORIZON_S = 6         # ml/label.py: "will degrade in the next 6 s"


def rules_for(src):
    """Recorded runs are judged by the rules they ran with (the experiment's), live runs by the current file."""
    if src.kind == 'replay':
        from dashboards.web import policy
        return policy.default()
    return POLICY


def pct(v):
    return f'{round(v * 100)}%'


def an(word):
    return ('an ' if word[0] in 'aeiou' else 'a ') + word


# ------------------------------------------------------------------ the trust check, step by step

def target_of(tick):
    return tick['a1'][5:] if tick.get('a1', '').startswith('slow') else None


def trust_check(tick, mode, P=None):
    """Agent 2's reasoning on one snapshot, as a list of checks plus the verdict and its reason."""
    P = P or POLICY
    p, link, now, steady = tick['prob'], tick['link'], tick['now'], tick['steady']
    alarms, target = tick.get('alarms', 0), target_of(tick)
    warned = tick.get('warned', [])
    checks = []

    checks.append({'id': 'risk', 'title': 'Is a protected device at risk?',
                   'state': 'pass' if p >= config.WARN_PROB else 'ok',
                   'value': f'warning {p:.2f}, act from {config.WARN_PROB:.2f}',
                   'detail': (f"{len(warned)} protected device{'s' if len(warned) != 1 else ''} warned, "
                              f"{sum(P['protected'].get(d) == 'high' for d in warned)} of high importance.")
                             if warned else 'No protected device is warned.'})
    full = link >= config.LINK_FULL
    checks.append({'id': 'line', 'title': 'Is the shared line full?',
                   'state': 'na' if p < config.WARN_PROB else ('pass' if full else 'fail'),
                   'value': f'{pct(link)} used, full from {pct(config.LINK_FULL)}',
                   'detail': 'A real jam fills the line. A fault makes devices slow without filling it.'})
    if p < config.WARN_PROB:
        kind_text = 'nothing to name'
    elif full:
        kind_text = 'a jam (the line is full)'
    elif alarms >= config.FAULT_MIN:
        kind_text = f'an internet fault ({alarms} protected devices warned, {config.FAULT_MIN} or more)'
    else:
        kind_text = f'a device fault ({alarms} protected device{"s" if alarms != 1 else ""} warned, under {config.FAULT_MIN})'
    checks.append({'id': 'kind', 'title': 'Is it a jam?',
                   'state': 'na' if now == 'ok' else ('pass' if now == 'jam' else 'fail'),
                   'value': kind_text,
                   'detail': 'Only a jam can be fixed by slowing a device.'})
    rule = WAIT.get(now if now != 'ok' else 'jam')
    if now == 'ok':
        st, val = 'na', 'no problem this snapshot'
    elif steady == 'ok':
        st, val = 'wait', f"{an(now)} must show in {rule['hits']} of the last {rule['of_last']} snapshots"
    else:
        st, val = 'pass', f'a steady {steady}'
    checks.append({'id': 'steady', 'title': 'Has it lasted long enough?', 'state': st, 'value': val,
                   'detail': 'jam 1 of 1, internet fault 2 of 2, device fault 3 of 5 snapshots.'})
    if target:
        allowed = target in P['may_slow'] and target not in P['protected']
        checks.append({'id': 'policy', 'title': "Do the homeowner's rules allow it?",
                       'state': 'pass' if allowed else 'fail',
                       'value': (f"the {target} is on the may-slow list" if allowed
                                 else f"the {target} may not be slowed"),
                       'detail': (f"Slow to {P['min_rate_mbit']} Mbit/s, never lower. Undo after "
                                  f"{P['max_slow_s']} s at most. Check again after {P['recheck_every_s']} s. "
                                  f"Protected: {', '.join(P['protected'])}.")})
    else:
        checks.append({'id': 'policy', 'title': "Do the homeowner's rules allow it?", 'state': 'na',
                       'value': 'nothing proposed', 'detail': f"May be slowed: {', '.join(P['may_slow'])}."})

    verdict = {'APPROVE': 'ALLOW', 'REFUSE': 'DENY'}.get(tick['a2'], 'NO ACTION')
    if verdict == 'ALLOW':
        reason = (f"The line is {pct(link)} full, so this is a jam, and the homeowner allows slowing the {target}. "
                  f"Slow the {target} to {P['min_rate_mbit']} Mbit/s.")
    elif verdict == 'DENY':
        if steady == 'ok':
            reason = f'Not sure yet: {checks[3]["value"]} before anything is done.'
        elif steady == 'jam':
            reason = f'It is a jam, but the homeowner does not allow slowing the {target}.'
        else:
            reason = (f"The line is only {pct(link)} full, so this is {'an' if steady[0] == 'i' else 'a'} {steady}, not a jam. "
                      f"Slowing the {target} would not help, so it is not slowed.")
    else:
        reason = 'No protected device is at risk, so there is nothing to decide.'
    if mode == 'predict' and target:
        acted = f'Prediction-only mode: the {target} is slowed anyway, because this mode has no trust check.'
    elif mode == 'none':
        acted = 'Watch-only mode: nothing is ever slowed.'
    elif verdict == 'ALLOW':
        acted = f'The {target} is slowed (unless the agent is still waiting for its 10-second check).'
    else:
        acted = 'Nothing is slowed.'
    return {'checks': checks, 'verdict': verdict, 'reason': reason, 'acted': acted,
            'target': target, 'tell': tick.get('tell', '').replace('TELL HOMEOWNER: ', '')}


# ------------------------------------------------------------------ the camera around a moment

def median(xs):
    return round(statistics.median(xs), 1) if xs else None


def is_bad(r, normal):
    return r['rtt_ms'] is None or (r['loss_pct'] or 0) > 0 or r['rtt_ms'] > normal


def window(rows, times, a, b, normal):
    """The watched device's readings between a and b."""
    sel = rows[bisect.bisect_left(times, a):bisect.bisect_left(times, b)]
    if not sel:
        return None
    rtts = [r['rtt_ms'] for r in sel if r['rtt_ms'] is not None]
    return {'n': len(sel), 'rtt': median(rtts), 'loss': round(sum(r['loss_pct'] or 0 for r in sel) / len(sel), 1),
            'no_reply': sum(r['rtt_ms'] is None for r in sel),
            'bad_pct': round(100 * sum(is_bad(r, normal) for r in sel) / len(sel))}


def compare_windows(before, after):
    if not before or not after:
        return 'not measured yet'
    if before['bad_pct'] == 0 and after['bad_pct'] == 0:
        return 'was already fine'
    if after['bad_pct'] < before['bad_pct'] or (after['bad_pct'] == before['bad_pct'] and (after['rtt'] or 1e9) < (before['rtt'] or 1e9) * 0.8):
        return 'better'
    if after['bad_pct'] > before['bad_pct']:
        return 'worse'
    return 'no better'


# ------------------------------------------------------------------ the audit trail

def event_at(events, t, now):
    for e in events:
        if e['start'] - 2 <= t <= (e['end'] or now) + GRACE_S:
            return e
    return None


def truth(e, device):
    """Was this slow-down the right kind of action, according to the answer sheet (events log)?"""
    if e is None:
        return 'calm', 'No event was running: not needed'
    who = ', '.join(e['devices'])
    if e['type'] in JAMS:
        if device in e['devices']:
            return 'right', f"Jam ({e['type']}) by {who}: slowed a flooder"
        return 'partly', f"Jam ({e['type']}) by {who}: slowed a device that was not flooding"
    return 'wrong', f"{'Internet fault' if e['type'] == 'F_WAN' else 'Device fault on ' + who}: slowing cannot help"


def decisions(src):
    start, ticks, actions = src.agent(10 ** 6)
    mode = start.get('mode', '?')
    now = src.now()
    P = rules_for(src)
    w = config.WATCH
    normal = config.NORMAL_MS.get(w, 150)
    cam = src.metrics(w, 5000)
    ct = [r['timestamp'] for r in cam]
    events = src.events()
    tt = [t['t'] for t in ticks]

    def tick_before(t):
        i = bisect.bisect_right(tt, t) - 1
        return ticks[i] if i >= 0 else None

    def camera(t):
        b = window(cam, ct, t + BEFORE_S[0], t + BEFORE_S[1], normal)
        a = window(cam, ct, t + AFTER_S[0], t + AFTER_S[1], normal) if now >= t + AFTER_S[1] else None
        return b, a, compare_windows(b, a)

    out = []
    for i, a in enumerate(actions):
        if a['event'] not in ('SLOW', 'SLOW REFUSED'):
            continue
        tk = tick_before(a['t'] + 0.5)
        prev = actions[i - 1] if i else None
        why_now = ('the 10-second check found the jam still there' if prev and prev['event'] == 'CHECK'
                   and not prev.get('helped') and a['t'] - prev['t'] < 1 else 'the trust check allowed it'
                   if mode == 'trust' else 'Agent 1 proposed it (no trust check)')
        chk = next((c for c in actions[i + 1:] if c['event'] == 'CHECK' and c['t'] - a['t'] <= 20), None)
        und = next((u for u in actions[i + 1:] if u['event'] == 'UNDO' and u['device'] == a['device']), None)
        b, af, cv = camera(a['t'])
        e = event_at(events, a['t'], now)
        tv, tw = truth(e, a['device'])
        tc = trust_check(tk, mode, P) if tk else None
        out.append({
            'kind': 'slow' if a['event'] == 'SLOW' else 'blocked', 't': a['t'], 'mode': mode, 'device': a['device'],
            'prob': tk and tk['prob'], 'link': tk and tk['link'], 'diagnosis': tk and tk['steady'],
            'agent2': tc and tc['verdict'], 'agent2_reason': tc and tc['reason'], 'checks': tc and tc['checks'],
            'why_now': why_now,
            'action': (f"Slowed the {a['device']} to {P['min_rate_mbit']} Mbit/s" if a['event'] == 'SLOW'
                       else f"Could not slow the {a['device']}: {a.get('msg', '')}"),
            'check': (None if not chk else
                      f"after 10 s: {'it helped' if chk.get('helped') else 'still a jam'} "
                      f"(line {pct(chk.get('link_before') or 0)} to {pct(chk.get('link_now') or 0)})"),
            'kept': (f"undone after {und.get('after_s')} s ({und.get('reason')})" if und
                     else 'still slowed' if a['event'] == 'SLOW' else ''),
            'reverted_by': und and und.get('reason'),
            'camera_before': b, 'camera_after': af, 'camera_verdict': cv,
            'event': e and {'type': e['type'], 'devices': e['devices']}, 'truth': tv, 'truth_text': tw,
        })

    # refusals: runs of snapshots where Agent 1 wanted to slow and the trust check said no
    slow_t = [a['t'] for a in actions if a['event'] == 'SLOW']
    run = []

    def close(run):
        first, last = run[0], run[-1]
        kinds = Counter(r['steady'] for r in run)
        main = kinds.most_common(1)[0][0]
        tc = trust_check(next((r for r in run if r['steady'] == main), first), mode, P)
        acted = any(first['t'] - 1 <= t <= last['t'] + 2 for t in slow_t)
        if acted and mode == 'predict':
            return                      # already in the list as a slow-down marked "trust check: deny, ignored"
        b, af, cv = camera(first['t'])
        e = event_at(events, first['t'], now)
        if e is None:
            tv, tw = 'calm', 'No event was running: right not to act'
        elif e['type'] in JAMS:
            later = next((t for t in slow_t if last['t'] < t <= (e['end'] or now) + GRACE_S), None)
            before = [t for t in slow_t if e['start'] - 2 <= t <= first['t']]
            if before:
                tv, tw = 'handled', (f"Jam ({e['type']}) by {', '.join(e['devices'])} already handled: slowed "
                                     f"{round(first['t'] - before[-1])} s earlier, the line is no longer full")
            elif later:
                tv, tw = 'waited', (f"Jam ({e['type']}) by {', '.join(e['devices'])} just starting, line not full yet: "
                                    f"slowed {round(later - first['t'])} s later")
            else:
                tv, tw = 'missed', f"Jam ({e['type']}) by {', '.join(e['devices'])}: a slow-down was needed"
        else:
            tv, tw = 'right', f"{'Internet fault' if e['type'] == 'F_WAN' else 'Device fault on ' + ', '.join(e['devices'])}: right not to slow"
        if acted:
            tv, tw = ('wrong' if tv == 'right' else tv), tw.replace('right not to slow', 'slowing cannot help')
        out.append({
            'kind': 'refuse', 't': first['t'], 'until': last['t'], 'snapshots': len(run), 'mode': mode,
            'device': target_of(first), 'prob': max(r['prob'] for r in run), 'link': max(r['link'] for r in run),
            'diagnosis': main, 'agent2': 'DENY', 'agent2_reason': tc['reason'], 'checks': tc['checks'],
            'why_now': 'Agent 1 proposed it',
            'action': (f"Slowed anyway (prediction-only mode)" if acted and mode == 'predict'
                       else 'Not slowed' + (' (watch-only mode)' if mode == 'none' else '')),
            'check': None, 'kept': '', 'reverted_by': None,
            'tell': next((r['tell'].replace('TELL HOMEOWNER: ', '') for r in run if r.get('tell')), ''),
            'camera_before': b, 'camera_after': af, 'camera_verdict': cv,
            'event': e and {'type': e['type'], 'devices': e['devices']}, 'truth': tv, 'truth_text': tw,
        })

    for r in ticks:
        if r['a1'].startswith('slow') and r['a2'] == 'REFUSE':
            if run and r['t'] - run[-1]['t'] > 4.5:
                close(run)
                run = []
            run.append(r)
        elif run and r['t'] - run[-1]['t'] > 4.5:
            close(run)
            run = []
    if run:
        close(run)
    out.sort(key=lambda d: d['t'], reverse=True)
    return {'mode': mode, 'now': now, 'watch': w, 'normal_ms': normal, 'records': out,
            'counts': Counter(d['kind'] for d in out)}


DECISION_COLS = ['time', 'kind', 'mode', 'device', 'prob', 'link', 'diagnosis', 'agent2', 'agent2_reason',
                 'action', 'check', 'kept', 'camera_rtt_before', 'camera_rtt_after', 'camera_bad_before_pct',
                 'camera_bad_after_pct', 'camera_verdict', 'event', 'truth', 'truth_text']


def decisions_csv_rows(d):
    for r in d['records']:
        b, a = r['camera_before'] or {}, r['camera_after'] or {}
        yield {'time': round(r['t'], 2), 'kind': r['kind'], 'mode': r['mode'], 'device': r['device'],
               'prob': r['prob'], 'link': r['link'], 'diagnosis': r['diagnosis'], 'agent2': r['agent2'],
               'agent2_reason': r['agent2_reason'], 'action': r['action'], 'check': r['check'] or '',
               'kept': r['kept'], 'camera_rtt_before': b.get('rtt'), 'camera_rtt_after': a.get('rtt'),
               'camera_bad_before_pct': b.get('bad_pct'), 'camera_bad_after_pct': a.get('bad_pct'),
               'camera_verdict': r['camera_verdict'], 'event': (r['event'] or {}).get('type', 'calm'),
               'truth': r['truth'], 'truth_text': r['truth_text']}


# ------------------------------------------------------------------ the watched device, last 10 minutes

def camera(src, span=600):
    w = config.WATCH
    now = src.now()
    rows = [r for r in src.metrics(w, span // config.INTERVAL + 20) if r['timestamp'] >= now - span]
    _, _, actions = src.agent(10)
    d = decisions(src)
    last = next((r for r in d['records'] if r['kind'] == 'slow'), None)
    m = rows[-1] if rows else {}
    base = window(rows, [r['timestamp'] for r in rows], now - 60, now + 1, d['normal_ms'])
    return {'device': w, 'normal_ms': d['normal_ms'], 'now': now, 'latest': m, 'last_minute': base,
            'series': [[r['timestamp'], r['rtt_ms'], r['loss_pct']] for r in rows],
            'events': [e for e in src.events() if (e['end'] or now) >= now - span],
            'actions': [{'t': a['t'], 'event': a['event'], 'device': a.get('device')} for a in actions
                        if a['t'] >= now - span and a['event'] in ('SLOW', 'UNDO', 'CHECK')],
            'last_slow': last}


# ------------------------------------------------------------------ the comparison (recorded experiment)

_memo = {}


def memo(key, files, fn):
    stamp = tuple(os.path.getmtime(f) if os.path.exists(f) else 0 for f in files)
    hit = _memo.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    val = fn()
    _memo[key] = (stamp, val)
    return val


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            try:
                r[k] = float(v) if v not in ('', None) and not k.endswith(('type', 'mode', 'devices', 'named_as')) else v
            except ValueError:
                pass
    return rows


def recovery_s(rows, times, e, normal):
    """Seconds from the event start until the camera has 3 good readings in a row (None = not by end + 30 s)."""
    sel = rows[bisect.bisect_left(times, e['start']):bisect.bisect_left(times, e['end'] + RECOVERY_S)]
    good = 0
    for r in sel:
        good = 0 if is_bad(r, normal) else good + 1
        if good == 3:
            return round(r['timestamp'] - e['start'], 1)
    return None


def _compare():
    from dashboards.web import policy
    POLICY = policy.default()               # the recorded runs used the experiment's rules
    ev = read_csv(os.path.join(config.RESULTS_DIR, 'events_scored.csv'))
    runs = read_csv(os.path.join(config.RESULTS_DIR, 'runs_scored.csv'))
    sess = sources.list_sessions()
    w, normal = config.WATCH, config.NORMAL_MS.get(config.WATCH, 150)
    cam_rows, violations, schedules = [], {m: [] for m in config.MODES}, {}
    for s in sess:
        S = sources.session(s['session'])
        rows, times = S.rows.get(w, []), S.times.get(w, [])
        tick0, tick1 = (S.tick_t[0], S.tick_t[-1]) if S.tick_t else (S.t0, S.t1)
        for e in S.all_events:
            if not e['end'] or e['start'] < tick0 or e['end'] > tick1:
                continue
            win = window(rows, times, e['start'], e['end'], normal)
            cam_rows.append({'session': s['session'], 'seed': s['seed'], 'mode': s['mode'], 'type': e['type'],
                             'devices': '|'.join(e['devices']), 'start_s': round(e['start'] - S.t0),
                             'camera_bad_pct': win and win['bad_pct'], 'camera_rtt_median': win and win['rtt'],
                             'camera_loss_pct': win and win['loss'],
                             'camera_recovery_s': recovery_s(rows, times, e, normal) if e['type'] in JAMS else None})
        open_ = {}
        for a in S.actions:
            if a['event'] == 'SLOW':
                open_[a['device']] = a['t']
                if a['device'] not in POLICY['may_slow']:
                    violations[s['mode']].append(f"session {s['session']}: slowed protected device {a['device']}")
                try:
                    kbit = float(a.get('msg', '').split('now ')[1].split(' ')[0])
                    if kbit < POLICY['min_rate_mbit'] * 1000:
                        violations[s['mode']].append(f"session {s['session']}: {a['device']} below the floor")
                except (IndexError, ValueError):
                    pass
            elif a['event'] == 'UNDO':
                open_.pop(a['device'], None)
                if (a.get('after_s') or 0) > POLICY['max_slow_s'] + 2 * config.INTERVAL + 1:
                    violations[s['mode']].append(f"session {s['session']}: {a['device']} slowed {a['after_s']} s")
        for d, t in open_.items():          # still slowed when the run ended: only a problem if past the limit
            if tick1 - t > POLICY['max_slow_s'] + 2 * config.INTERVAL + 1:
                violations[s['mode']].append(f"session {s['session']}: {d} never undone")
        schedules.setdefault(s['seed'], {})[s['mode']] = json.dumps(
            [(x['type'], x['t_start'], x['duration'], x['params']) for x in S.meta.get('schedule', [])], sort_keys=True)

    same = {seed: len(set(v.values())) == 1 and len(v) == len(config.MODES) for seed, v in schedules.items()}
    M = {}
    for m in config.MODES:
        J = [r for r in ev if r['mode'] == m and r['type'] in JAMS]
        F = [r for r in ev if r['mode'] == m and r['type'] in FAULTS]
        R = [r for r in runs if r['mode'] == m]
        CJ = [r for r in cam_rows if r['mode'] == m and r['type'] in JAMS]
        CF = [r for r in cam_rows if r['mode'] == m and r['type'] in FAULTS]
        calm_h = sum(r['calm_hours'] for r in R)
        slows_j = sum(r['slowdowns'] for r in J)
        rec = [r['camera_recovery_s'] for r in CJ]
        firsts = [r['first_slow_s'] for r in J if r['first_slow_s'] != '']
        M[m] = {
            'runs': len(R), 'jams': len(J), 'faults': len(F),
            'jams_acted_pct': 100 * sum(r['slowdowns'] > 0 for r in J) / len(J) if J else None,
            'missed_jams': sum(r['slowdowns'] == 0 for r in J) if m != 'none' else len(J),
            'first_slow_s': statistics.median(firsts) if firsts else None,
            'hit_flooder_pct': 100 * sum(r['slowed_flooder'] for r in J) / slows_j if slows_j else None,
            'unsafe_faults_pct': 100 * sum(r['slowdowns'] > 0 for r in F) / len(F) if F else None,
            'unsafe_slowdowns': sum(r['slowdowns'] for r in F),
            'fault_slowed_s': sum(r['slowed_seconds'] for r in F),
            'calm_hours': calm_h,
            'calm_per_hour': sum(r['calm_slowdowns'] for r in R) / calm_h if calm_h else None,
            'calm_messages_per_hour': sum(r['calm_messages'] for r in R) / calm_h if calm_h else None,
            'protected_bad_jams_pct': statistics.mean(r['protected_bad_pct'] for r in J if r['protected_bad_pct'] != '') if J else None,
            'protected_bad_faults_pct': statistics.mean(r['protected_bad_pct'] for r in F if r['protected_bad_pct'] != '') if F else None,
            'camera_bad_jams_pct': statistics.mean(r['camera_bad_pct'] for r in CJ if r['camera_bad_pct'] is not None) if CJ else None,
            'camera_rtt_jams_ms': statistics.median(r['camera_rtt_median'] for r in CJ if r['camera_rtt_median']) if CJ else None,
            'camera_loss_jams_pct': statistics.mean(r['camera_loss_pct'] for r in CJ if r['camera_loss_pct'] is not None) if CJ else None,
            'camera_recovery_s': statistics.median([x for x in rec if x is not None]) if any(x is not None for x in rec) else None,
            'camera_not_recovered': sum(x is None for x in rec),
            'camera_bad_faults_pct': statistics.mean(r['camera_bad_pct'] for r in CF if r['camera_bad_pct'] is not None) if CF else None,
            'policy_violations': len(violations[m]), 'violation_list': violations[m][:20],
            'diagnosis_right_pct': (100 * sum(r['name_right'] for r in ev if r['mode'] == m) /
                                    max(1, sum(1 for r in ev if r['mode'] == m))) if m == 'trust' else None,
            'errors': sum(r['errors'] for r in R),
        }
    by_type = {}
    for t in JAMS + FAULTS:
        by_type[t] = {}
        for m in config.MODES:
            these = [r for r in ev if r['mode'] == m and r['type'] == t and r['protected_bad_pct'] != '']
            cams = [r for r in cam_rows if r['mode'] == m and r['type'] == t and r['camera_bad_pct'] is not None]
            by_type[t][m] = {'events': len(these),
                             'protected_bad_pct': statistics.mean(r['protected_bad_pct'] for r in these) if these else None,
                             'camera_bad_pct': statistics.mean(r['camera_bad_pct'] for r in cams) if cams else None}
    return {'found': bool(ev and runs), 'sessions': sess, 'same_schedule': same, 'modes': M,
            'by_type': by_type, 'events': ev, 'camera_events': cam_rows, 'watch': w,
            'results_dir': config.RESULTS_DIR, 'exp_dir': config.EXP_DIR}


def compare():
    files = [os.path.join(config.RESULTS_DIR, f) for f in ('events_scored.csv', 'runs_scored.csv')]
    return memo('compare', files, _compare)


COMPARE_COLS = [('jams_acted_pct', 'Jams acted on (%)'), ('missed_jams', 'Missed jams (no slow-down)'),
                ('first_slow_s', 'Time to first slow-down (median s)'), ('hit_flooder_pct', 'Slow-downs that hit a flooder (%)'),
                ('unsafe_faults_pct', 'Faults with a wrong slow-down (%)'), ('unsafe_slowdowns', 'Wrong slow-downs during faults'),
                ('fault_slowed_s', 'Device-seconds slowed during faults'), ('calm_per_hour', 'Slow-downs in calm time per hour'),
                ('calm_messages_per_hour', 'Homeowner messages in calm time per hour'),
                ('protected_bad_jams_pct', 'Protected readings bad during jams (%)'),
                ('camera_bad_jams_pct', 'Camera readings bad during jams (%)'),
                ('camera_rtt_jams_ms', 'Camera delay during jams (median ms)'),
                ('camera_loss_jams_pct', 'Camera ping loss during jams (mean %)'),
                ('camera_recovery_s', 'Camera back to normal after a jam starts (median s)'),
                ('camera_not_recovered', 'Jams where the camera did not recover'),
                ('policy_violations', 'Homeowner rule violations'), ('diagnosis_right_pct', 'Events named right (%)')]


# ------------------------------------------------------------------ Agent 1's reliability (recorded no-agent runs)

def degraded_soon(S):
    """For each protected device: times when it was degraded (ml/label.py: 2 of the last 3 readings bad)."""
    out = []
    for d in config.PROTECTED:
        rows, normal, last = S.rows.get(d, []), config.NORMAL_MS[d], []
        for r in rows:
            last = (last + [is_bad(r, normal)])[-3:]
            if sum(last) >= 2:
                out.append(r['timestamp'])
    return sorted(out)


def _model():
    runs = [s for s in sources.list_sessions() if s['mode'] == 'none']
    ticks_all, ev_all = [], []
    for s in runs:
        S = sources.session(s['session'])
        deg = degraded_soon(S)
        evs = [e for e in S.all_events if e['end']]
        busy = [(e['start'], e['end'] + RECOVERY_S) for e in evs]
        for t in S.ticks:
            i = bisect.bisect_right(deg, t['t'])
            soon = i < len(deg) and deg[i] <= t['t'] + HORIZON_S
            calm = not any(a <= t['t'] <= b for a, b in busy)
            ticks_all.append((t['prob'], soon, calm))
        for e in evs:
            if S.tick_t and S.tick_t[0] <= e['start'] and e['end'] <= S.tick_t[-1]:
                probs = [(t['t'] - e['start'], t['prob']) for t in S.ticks if e['start'] <= t['t'] <= e['end']]
                ev_all.append((e['type'], probs))
    calm_n = sum(1 for _, _, c in ticks_all if c)
    calm_h = calm_n * config.INTERVAL / 3600
    sweep = []
    for k in range(1, 20):
        th = k / 20
        jams = [p for ty, p in ev_all if ty in JAMS]
        faults = [p for ty, p in ev_all if ty in FAULTS]
        caught = [next((dt for dt, p in ps if p >= th), None) for ps in jams]
        delays = [d for d in caught if d is not None]
        warned_f = [any(p >= th for _, p in ps) for ps in faults]
        calm_w = sum(1 for p, _, c in ticks_all if c and p >= th)
        tp = sum(1 for p, y, _ in ticks_all if p >= th and y)
        fp = sum(1 for p, y, _ in ticks_all if p >= th and not y)
        fn = sum(1 for p, y, _ in ticks_all if p < th and y)
        sweep.append({'threshold': th,
                      'jams_caught_pct': 100 * len(delays) / len(jams) if jams else None,
                      'warning_delay_s': statistics.median(delays) if delays else None,
                      'faults_warned_pct': 100 * sum(warned_f) / len(warned_f) if warned_f else None,
                      'calm_warnings_per_hour': calm_w / calm_h if calm_h else None,
                      'precision': tp / (tp + fp) if tp + fp else None,
                      'recall': tp / (tp + fn) if tp + fn else None})
    bins = []
    for b in range(10):
        lo, hi = b / 10, (b + 1) / 10
        sel = [(p, y) for p, y, _ in ticks_all if lo <= p < hi or (b == 9 and p == 1.0)]
        bins.append({'lo': lo, 'hi': hi, 'n': len(sel),
                     'mean_prob': statistics.mean(p for p, _ in sel) if sel else None,
                     'observed': sum(y for _, y in sel) / len(sel) if sel else None})
    n = len(ticks_all)
    brier = sum((p - y) ** 2 for p, y, _ in ticks_all) / n if n else None
    ece = sum(b['n'] / n * abs(b['mean_prob'] - b['observed']) for b in bins if b['n']) if n else None
    base = sum(y for _, y, _ in ticks_all) / n if n else None
    return {'runs': [s['session'] for s in runs], 'snapshots': n, 'calm_hours': calm_h,
            'jams': sum(1 for ty, _ in ev_all if ty in JAMS), 'faults': sum(1 for ty, _ in ev_all if ty in FAULTS),
            'sweep': sweep, 'bins': bins, 'brier': brier, 'ece': ece, 'base_rate': base,
            'threshold': config.WARN_PROB, 'offline': offline_scores()}


def offline_scores():
    """The out-of-fold scores printed by the training notebook (its own output, not retyped)."""
    try:
        nb = json.load(open(config.NOTEBOOK))
    except (OSError, ValueError):
        return None
    for c in nb.get('cells', []):
        for o in c.get('outputs', []):
            text = ''.join(o.get('text', '')) or ''.join(o.get('data', {}).get('text/plain', ''))
            if 'trained model' in text and 'precision' in text:
                lines = [l for l in text.splitlines() if l.strip()]
                head = lines[0].split()
                rows = []
                for l in lines[1:]:
                    parts = l.split()
                    vals = parts[-len(head) + 1:]
                    rows.append({'model': ' '.join(parts[:len(parts) - len(vals)]),
                                 **{h: logs.sf(v) for h, v in zip(head[1:], vals)}})
                return {'source': config.NOTEBOOK, 'rows': rows,
                        'note': 'Out-of-fold scores on the 40 training sessions, protected devices only.'}
    return None


def model_report():
    files = [os.path.join(config.EXP_DIR, 'runs.log'), config.NOTEBOOK]
    return memo('model', files, _model)


SWEEP_COLS = ['threshold', 'jams_caught_pct', 'warning_delay_s', 'faults_warned_pct', 'calm_warnings_per_hour',
              'precision', 'recall']


# ------------------------------------------------------------------ messages to the homeowner

def messages(src, n=4000):
    """Every new message the agent sent the homeowner, and whether it was right (events log)."""
    _, ticks, _ = src.agent(n)
    now = src.now()
    events = src.events()
    out, prev = [], ''
    for t in ticks:
        tell = t.get('tell', '')
        if tell and tell != prev:
            text = tell.replace('TELL HOMEOWNER: ', '')
            named = text.split(' on ', 1)[1].split(',') if 'device problem on' in text else []
            e = event_at(events, t['t'], now)
            if 'internet' in text:
                verdict = 'right' if e and e['type'] == 'F_WAN' else 'wrong'
            elif e and e['type'] == 'F_DEVLINK':
                hit = [d for d in named if d in e['devices']]
                verdict = 'right' if hit and len(named) == 1 else 'partly' if hit else 'wrong'
            else:
                verdict = 'wrong'
            truth = (f"{e['type']} on {', '.join(e['devices'])}" if e else 'no event running')
            out.append({'t': t['t'], 'until': t['t'], 'text': text, 'named': named,
                        'kind': 'internet' if 'internet' in text else 'device',
                        'event': truth, 'verdict': verdict})
        elif tell and out and tell == prev:
            out[-1]['until'] = t['t']
        prev = tell
    return out
