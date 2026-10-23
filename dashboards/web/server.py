#!/usr/bin/env python3
"""
server.py - the Home Network Agent dashboard (web).
Live:   reads the Mininet logs in /tmp and the agent's log.
Replay: reads a recorded session from data/raw and data/experiment2.
Nothing to install (Python's own web server).

Run from the project root, in its own terminal:
    .venv/bin/python -m dashboards.web.server            # watch only
    sudo .venv/bin/python -m dashboards.web.server       # also start/stop the agent from the page
then open http://127.0.0.1:8081
"""
import argparse
import csv
import io
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from dashboards.web import api, config, control, insights, policy, sources

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')


def clean(x):
    """JSON has no NaN or Infinity: send them as null."""
    if isinstance(x, float) and (x != x or x in (float('inf'), float('-inf'))):
        return None
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def to_csv(rows, cols):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction='ignore')
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


class Handler(SimpleHTTPRequestHandler):
    """Files from static/, and JSON answers under /api/."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC, **kwargs)

    def end_headers(self):
        if not self.path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-cache')     # always check for a newer page, css or js
        super().end_headers()

    def send_body(self, code, body, ctype, filename=None):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, code, data, filename=None):
        self.send_body(code, json.dumps(clean(data), default=str), 'application/json', filename)

    def do_GET(self):
        u = urlparse(self.path)
        if not u.path.startswith('/api/'):
            return super().do_GET()                          # index.html, css, js
        q = parse_qs(u.query)
        n = q.get('n', ['720'])[0]
        n = max(10, min(20000, int(n))) if n.isdigit() else 720
        try:
            src = sources.get(q, self.server.agent_log)
            p = u.path
            if p == '/api/config':
                self.send_json(200, config.for_page())
            elif p == '/api/live':
                self.send_json(200, api.live(src))
            elif p.startswith('/api/device/') and p.split('/')[-1] in config.DEVICES:
                self.send_json(200, api.device(src, p.split('/')[-1], n))
            elif p == '/api/agent':
                self.send_json(200, api.agent(src))
            elif p == '/api/camera':
                self.send_json(200, insights.camera(src))
            elif p == '/api/decisions':
                self.send_json(200, insights.decisions(src))
            elif p == '/api/sessions':
                self.send_json(200, sources.list_sessions())
            elif p == '/api/compare':
                self.send_json(200, insights.compare())
            elif p == '/api/policy':
                self.send_json(200, policy.state())
            elif p == '/api/model':
                self.send_json(200, insights.model_report())
            elif p == '/api/export/decisions.csv':
                d = insights.decisions(src)
                self.send_body(200, to_csv(insights.decisions_csv_rows(d), insights.DECISION_COLS), 'text/csv',
                               f"decisions_{src.info().get('session', 'live')}.csv")
            elif p == '/api/export/decisions.json':
                self.send_json(200, insights.decisions(src), f"decisions_{src.info().get('session', 'live')}.json")
            elif p == '/api/export/compare.csv':
                c = insights.compare()
                rows = [{'measure': label, **{m: c['modes'][m].get(k) for m in config.MODES}}
                        for k, label in insights.COMPARE_COLS]
                self.send_body(200, to_csv(rows, ['measure'] + config.MODES), 'text/csv', 'comparison.csv')
            elif p == '/api/export/camera_events.csv':
                c = insights.compare()
                cols = list(c['camera_events'][0].keys()) if c['camera_events'] else ['session']
                self.send_body(200, to_csv(c['camera_events'], cols), 'text/csv', 'camera_per_event.csv')
            elif p == '/api/export/sweep.csv':
                self.send_body(200, to_csv(insights.model_report()['sweep'], insights.SWEEP_COLS), 'text/csv',
                               'threshold_sweep.csv')
            else:
                self.send_json(404, {'error': 'not found'})
        except Exception as e:
            self.send_json(500, {'error': f'{type(e).__name__}: {e}'})

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if self.headers.get('X-Dashboard') != '1':      # only this page may change things (no other website)
            return self.send_json(403, {'ok': False, 'message': 'Changes are only accepted from the dashboard page.'})
        if u.path in ('/api/policy', '/api/policy/reset'):
            try:
                if u.path == '/api/policy':
                    body = self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0)
                    ok, errors = policy.save(json.loads(body or b'{}'))
                else:
                    ok, errors = policy.reset()
            except (OSError, ValueError) as e:
                ok, errors = False, [f'Could not save: {e}']
            return self.send_json(200 if ok else 400, {'ok': ok, 'errors': errors, **policy.state(),
                                                       'agent': control.status()})
        if u.path == '/api/agent/restart':
            ok, msg = control.stop()
            if ok:
                ok, msg = control.start(q.get('mode', ['trust'])[0], self.server.agent_log)
                msg = msg.replace('started', 'restarted with the new rules') if ok else msg
            return self.send_json(200 if ok else 409, {'ok': ok, 'message': msg, **control.status()})
        if u.path == '/api/agent/start':
            ok, msg = control.start(q.get('mode', ['trust'])[0], self.server.agent_log)
        elif u.path == '/api/agent/stop':
            ok, msg = control.stop()
        else:
            return self.send_json(404, {'error': 'not found'})
        self.send_json(200 if ok else 409, {'ok': ok, 'message': msg, **control.status()})

    def log_message(self, *args):
        pass                                                 # keep the terminal quiet


def main():
    p = argparse.ArgumentParser(description='Home Network Agent dashboard (web)')
    p.add_argument('--port', type=int, default=8081)
    p.add_argument('--host', default='127.0.0.1', help='127.0.0.1 = this computer only')
    p.add_argument('--agent-log', default=config.AGENT_LOG, help="the live agent's log (run_agent.py --log)")
    args = p.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.agent_log = args.agent_log
    print(f'Home network agent dashboard: http://127.0.0.1:{args.port}')
    print(f'Live logs: /tmp and {args.agent_log}. Replay: {config.RAW_DIR} + {config.EXP_DIR}.')
    print('Agent control from the page: ' + ('on (running as root)' if control.can_control()
                                              else 'off (start the dashboard with sudo to turn it on)'))
    print('Press Ctrl+C to stop.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')


if __name__ == '__main__':
    main()
