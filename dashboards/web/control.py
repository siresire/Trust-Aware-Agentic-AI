"""
control.py - start and stop the agent from the page.
The agent changes the switch (ovs-vsctl), so it needs root. This only works when the
dashboard itself was started with sudo; otherwise the page shows the command to type.
Stopping sends SIGTERM: run_agent.py then undoes every slow-down before it exits.
"""
import os
import signal
import subprocess
import sys
import time

from dashboards.web import config

CMD = 'sudo .venv/bin/python -m agent.run_agent --mode {mode}'


def can_control():
    return hasattr(os, 'geteuid') and os.geteuid() == 0


def running():
    """PIDs of every agent.run_agent process on this machine (started here or by hand)."""
    pids = []
    for d in os.listdir('/proc'):
        if not d.isdigit():
            continue
        try:
            argv = open(f'/proc/{d}/cmdline', 'rb').read().split(b'\0')
        except OSError:
            continue
        if b'-m' in argv and b'agent.run_agent' in argv:
            pids.append(int(d))
    return pids


def status():
    return {'can_control': can_control(), 'running': bool(running()), 'pids': running(),
            'command': CMD.format(mode='trust')}


def start(mode, log_path):
    if mode not in config.MODES:
        return False, f'unknown mode {mode}'
    if not can_control():
        return False, 'The dashboard was not started with sudo, so it cannot start the agent. Type: ' + CMD.format(mode=mode)
    if running():
        return False, 'The agent is already running. Stop it first.'
    if not os.path.isdir('/tmp/network_metrics'):
        return False, 'The network is not running. Start the Mininet topology first.'
    os.makedirs(os.path.dirname(config.AGENT_OUT), exist_ok=True)
    out = open(config.AGENT_OUT, 'w')
    subprocess.Popen([sys.executable, '-m', 'agent.run_agent', '--mode', mode, '--log', log_path],
                     stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(20):                       # wait up to 2 s for it to appear
        if running():
            return True, f'Agent started in {mode} mode.'
        time.sleep(0.1)
    return False, 'The agent did not start. See ' + config.AGENT_OUT


def stop():
    pids = running()
    if not pids:
        return True, 'The agent was not running.'
    if not can_control():
        return False, 'The dashboard was not started with sudo. Press Ctrl+C in the agent terminal.'
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)       # run_agent undoes every slow-down, then exits
        except OSError:
            pass
    for _ in range(50):
        if not running():
            return True, 'Agent stopped. Every slow-down was undone.'
        time.sleep(0.1)
    return False, 'The agent is still stopping.'
