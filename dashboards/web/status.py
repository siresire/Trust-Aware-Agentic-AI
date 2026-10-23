"""
status.py - how healthy one device is, from its newest sample.
Each device is judged against its OWN normal delay (config_ubuntu.yaml), like the agent.
"""
from dashboards.web import config

CRIT_X = 2          # delay above 2 x normal = critical


def check(name, m, tcp_prev, tcp_last, now):
    """-> (status, issues). status is healthy / warning / critical / stale / offline."""
    if not m:
        return 'offline', []
    if now - m['timestamp'] > config.STALE_AFTER:
        return 'stale', []
    normal = config.NORMAL_MS.get(name, 150)
    issues = []
    rtt, loss = m['rtt_ms'], m['loss_pct']
    if rtt is None:
        issues.append({'level': 'critical', 'text': 'no ping reply'})
    elif rtt >= CRIT_X * normal:
        issues.append({'level': 'critical', 'text': 'RTT %.0f ms (normal %.0f)' % (rtt, normal)})
    elif rtt > normal:
        issues.append({'level': 'warning', 'text': 'RTT %.0f ms (normal %.0f)' % (rtt, normal)})
    if loss:
        issues.append({'level': 'critical' if loss >= 66 else 'warning', 'text': 'packet loss %.0f%%' % loss})
    if tcp_prev and tcp_last and now - tcp_last['timestamp'] <= config.STALE_AFTER:
        new = tcp_last['retrans_total'] - tcp_prev['retrans_total']
        if new > 0:
            issues.append({'level': 'warning', 'text': 'TCP retransmits +%d' % new})
    if any(i['level'] == 'critical' for i in issues):
        return 'critical', issues
    return ('warning' if issues else 'healthy'), issues
