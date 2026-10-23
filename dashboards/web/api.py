"""
api.py - builds the JSON answers the page asks for. Every function takes a source
(sources.Live or sources.Replay), so the same page works live and in replay.
"""
from dashboards.web import config, control, insights, status

RIBBON = 300            # agent snapshots for the 10-minute strip: 300 x 2 s


def agent_brief(src):
    """The agent's newest snapshot, with the trust check worked out step by step."""
    start, ticks, _ = src.agent(5)
    if not ticks:
        return None
    t = ticks[-1]
    mode = start.get('mode', '?')
    return {'mode': mode, 'age': round(src.now() - t['t'], 1), **t,
            'decision': insights.trust_check(t, mode, insights.rules_for(src))}


def live(src, spark=60):
    """Every device right now, plus the shared line, the events and the agent's newest snapshot."""
    now = src.now()
    proto = src.protocols()
    devices = {}
    for name in config.DEVICES:
        mh = src.metrics(name, spark)
        th = src.tcp(name, 3)
        m = mh[-1] if mh else {}
        st, issues = status.check(name, m, th[-2] if len(th) > 1 else None, th[-1] if th else None, now)
        devices[name] = {'name': name, 'type': config.TYPES.get(name, 'IoT'), 'protocol': proto.get(name),
                         'protected': name in config.PROTECTED,
                         'importance': config.POLICY['protected'].get(name),
                         'normal_ms': config.NORMAL_MS.get(name),
                         'status': st, 'issues': issues, 'metrics': m,
                         'age': round(now - m['timestamp'], 2) if m else None,
                         'spark': [[r['timestamp'], r['rtt_ms'], r['tx_kbps'], r['loss_pct']] for r in mh]}
    fresh = [d for d in devices.values() if d['status'] in ('healthy', 'warning', 'critical')]
    wan = src.metrics('router_wan', 300)
    if wan and now - wan[-1]['timestamp'] <= config.STALE_AFTER:
        up = wan[-1]['tx_kbps']                           # what leaves the router (the agent's number)
    else:
        up = sum(d['metrics']['tx_kbps'] for d in fresh)  # fallback: add up the devices
    events = src.events()
    ages = [d['age'] for d in devices.values() if d['age'] is not None]
    return {'now': now, 'source': src.info(), 'devices': devices, 'agent': agent_brief(src),
            'uplink': {'kbps': round(up, 1), 'util': round(up / config.LINK_KBPS, 4),
                       'history': [[r['timestamp'], round(r['tx_kbps'] / config.LINK_KBPS, 4)] for r in wan]},
            'summary': {'online': len(fresh),
                        'healthy': sum(d['status'] == 'healthy' for d in fresh),
                        'warning': sum(d['status'] == 'warning' for d in fresh),
                        'critical': sum(d['status'] == 'critical' for d in fresh)},
            'event_now': next((e for e in reversed(events) if e['end'] is None), None),
            'events': [e for e in events if (e['end'] or now) >= now - 600],
            'data_age': min(ages) if ages else None,
            'messages': insights.messages(src)[-6:],
            'logs_found': bool(src.metrics(config.WATCH, 1)),
            'control': control.status() if src.kind == 'live' else None}


def device(src, name, n):
    return {'name': name, 'type': config.TYPES.get(name), 'protocol': src.protocols().get(name),
            'protected': name in config.PROTECTED, 'normal_ms': config.NORMAL_MS.get(name), 'now': src.now(),
            'history': src.metrics(name, n), 'tcp_history': src.tcp(name, n)}


def agent(src):
    """The last 10 minutes of the agent, and counts for the whole run."""
    start, ticks, actions = src.agent(20000)
    last = ticks[-1] if ticks else None
    totals = {
        'minutes': round((ticks[-1]['t'] - ticks[0]['t']) / 60, 1) if len(ticks) > 1 else 0,
        'a1_slow': sum(t['a1'].startswith('slow') for t in ticks),
        'approve': sum(t['a2'] == 'APPROVE' for t in ticks),
        'refuse': sum(t['a2'] == 'REFUSE' for t in ticks),
        'slows': sum(a['event'] == 'SLOW' for a in actions),
        'undos': sum(a['event'] == 'UNDO' for a in actions),
        'messages': sum(1 for i, t in enumerate(ticks)
                        if t['tell'] and (i == 0 or ticks[i - 1]['tell'] != t['tell'])),
        'errors': sum(a['event'] == 'ERROR' for a in actions),
    }
    return {'now': src.now(), 'mode': start.get('mode'),
            'age': round(src.now() - last['t'], 1) if last else None,
            'last': last, 'ticks': ticks[-RIBBON:], 'actions': actions[-60:], 'totals': totals}
