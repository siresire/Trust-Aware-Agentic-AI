import json
import subprocess
import sys
from pathlib import Path

# project folder = one level up from agent/
ROOT = Path(__file__).resolve().parent.parent
POLICY = json.loads((ROOT / "models" / "homeowner_policy.json").read_text())

# which switch port each device the agent may slow is plugged into (from "net")
PORTS = {"phone": "s1-eth8", "tv": "s1-eth9", "laptop": "s1-eth10"}


def set_limit(port, kbit):
    """put a speed limit on a switch port (0 = no limit)"""
    subprocess.run(["ovs-vsctl", "set", "interface", port,
                    f"ingress_policing_rate={kbit}",
                    f"ingress_policing_burst={kbit}"], check=True)


def get_limit(port):
    """read the current limit on a switch port, in kbit/s"""
    out = subprocess.run(["ovs-vsctl", "get", "interface", port, "ingress_policing_rate"],
                         capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


def slow_down(device, rate_mbit):
    """slow one device down, only if the homeowner rules allow it"""
    if device not in POLICY["may_slow"]:
        return False, f"refused: {device} is not on the may_slow list"
    if rate_mbit < POLICY["min_rate_mbit"]:
        return False, f"refused: {rate_mbit} Mbit/s is below the lowest allowed ({POLICY['min_rate_mbit']} Mbit/s)"
    kbit = int(rate_mbit * 1000)
    set_limit(PORTS[device], kbit)
    return True, f"{device} limited to {rate_mbit} Mbit/s (port {PORTS[device]}, now {get_limit(PORTS[device])} kbit/s)"


def undo(device):
    """take the limit off a device"""
    if device not in PORTS:
        return False, f"refused: {device} has no port the agent controls"
    set_limit(PORTS[device], 0)
    return True, f"{device} back to full speed (port {PORTS[device]}, now {get_limit(PORTS[device])} kbit/s)"


def show():
    """print the current limit on every device the agent may slow"""
    for d, p in PORTS.items():
        k = get_limit(p)
        print(f"  {d:7s} {p:9s} {'no limit' if k == 0 else f'{k} kbit/s'}")


if __name__ == "__main__":
    # sudo python3 agent/actions.py slow tv 2
    # sudo python3 agent/actions.py undo tv
    # sudo python3 agent/actions.py show
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "slow":
        ok, msg = slow_down(sys.argv[2], float(sys.argv[3]))
        print(msg)
    elif cmd == "undo":
        ok, msg = undo(sys.argv[2])
        print(msg)
    else:
        show()