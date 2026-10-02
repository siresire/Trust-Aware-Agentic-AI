# experiments/ — Schedules, unattended sessions, baseline, collection

This folder turns the `topo/` testbed into a dataset. It plans each session's events in
advance, runs sessions with no typing, checks their quality, measures what "normal" looks
like, and records many sessions overnight.

## Files

| File | Role |
|---|---|
| `__init__.py` | Makes `experiments/` a package |
| `scenarios.py` | Random but reproducible event schedule for one session, with `should_act` ground truth |
| `run_experiment.py` | Runs one unattended, labelled session and saves it to `data/raw/session_XXX/` |
| `check_session.py` | Quality check of one recorded session |
| `baseline.py` | Per-device normal ranges from the normal-only sessions |
| `collect_sessions.sh` | Records many sessions one after another |

## Run

Always from the project root.

```bash
python3 -m experiments.scenarios --seed 1                     # print a schedule (no sudo)
sudo python3 -m experiments.run_experiment --session 1        # one 30-minute session
sudo python3 -m experiments.run_experiment --session 101 --events 0   # normal-only session
python3 -m experiments.check_session data/raw/session_001     # check it
python3 -m experiments.baseline                               # baseline report
sudo nohup bash experiments/collect_sessions.sh 1 16 > /dev/null 2>&1 &   # overnight
```

Stop a collection politely with `touch data/STOP` (the current session finishes first).

Rule for imports in every folder: `import topo` first, then import topo files by plain name.

## Event mix

| Type | Weight | Parameters | should_act |
|---|---|---|---|
| C_SEVERE | 0.35 | 2–3 of laptop/phone/tv, 8–20 Mbit/s each | True |
| C_BORDER | 0.25 | 1 of laptop/phone/tv, 5–9 Mbit/s | True |
| F_WAN | 0.20 | WAN delay 60–150 ms, loss 3–10 % | False |
| F_DEVLINK | 0.20 | one of camera/doorbell/lock/thermostat/speaker, loss 10–30 % | False |

Every session starts with 120 s of normal traffic. Each event lasts 15–60 s and is followed by
a 45–120 s gap. `should_act` is True only when rate-limiting an allowed device can fix the event.
Over 40 seeds the plan gives 480 events, about 58 % True and 42 % False.

## What a session folder contains

```
data/raw/session_001/
├── network_metrics/      one log per device, plus router_lan.log and router_wan.log
├── tcp_metrics/          phone.log, laptop.log, tv.log
├── normal_traffic.log    mqtt_received.log    iperf_udp_server.log    iperf_tcp_server.log
├── events.log            raw START/END lines
├── events.csv            the same lines plus schedule_id and should_act
├── port_map.json
└── meta.json             seed, schedule, actual start times, git commit, warnings
```

## What the runner guarantees

| Guarantee | How |
|---|---|
| Clean start | Mininet cleanup before building the network |
| Events exactly as planned | Uses the schedule's own parameters |
| No overlapping events | Waits while a flood or fault is still running |
| Recovery time | At least 30 s after the last END line before the next event |
| Always shuts down | `try / finally`, also after Ctrl+C |
| Partial runs are marked | `"complete": false` in `meta.json` |
| Never overwrites data | Refuses if the session folder exists |
| Traceable | Records the git commit and whether code was uncommitted |

## Build log

### Step 18 — Event schedule (`scenarios.py`)
| Command | Expected |
|---|---|
| `python3 -m experiments.scenarios --seed 1` | 12 events, first `t_start` 120 |
| same command again | Identical table |
| `--seed 1 --events 0` | `0 events {}` |

### Step 21 — Unattended session (`run_experiment.py`, `check_session.py`)
| Command | Expected |
|---|---|
| `sudo python3 -m experiments.run_experiment --session 900 --seed 906 --duration 480 --events 4 --out data/test` | `Saved ... (complete=True, 0 warning(s))` |
| `python3 -m experiments.check_session data/test/session_900` | `rows with wrong column count: 0`; equal start/end counts per event |

`check_session` prints, for every event and protected device, the loss and RTT during the
event next to the device's normal RTT, and how long the device took to recover after END.

### Step 22 — Pilot, calibration, baseline, freeze

Calibration found in the pilot:

| Finding | Change |
|---|---|
| ping adds `, pipe N` under congestion, which broke about a third of the congested rows | `topo/network_monitor.py` takes only the numbers after `=` |
| F_WAN at 33 ms was barely visible (1.4 × normal RTT, 0 % loss) | F_WAN 60–150 ms and 3–10 %; F_DEVLINK 10–30 % |
| Floods overrun their planned length by 17–30 s while the queue drains | END lines record the real end; 30 s quiet rule in the runner |
| One flooder at 9 Mbit/s already caused 58 % loss on every device | C_BORDER 5–9 Mbit/s |

Signatures in the pilot (seed 1):

| Type | Who suffers | How |
|---|---|---|
| C_BORDER / C_SEVERE | every device | 58–86 % loss, RTT 440–775 ms |
| F_WAN | every device | RTT 146–172 ms, some loss |
| F_DEVLINK | only the target | 8–31 % loss; the others at normal RTT with 0 % loss |

Devices returned to normal within 0–11 s of each END line.

Baseline from sessions 101–103 (normal-only, first 30 s of each skipped):

| Measure | Value |
|---|---|
| Median RTT | 66.4–66.8 ms on nine devices, tv 76.8 ms |
| p99 RTT, protected devices | 102–105 ms |
| Rows with any lost ping, protected devices | 0.00–0.16 % |
| Shared uplink | p50 2412, p99 6710, max 7830 kbps of 10,000 |
| MQTT delay | p50 about 185 ms, p99 220–410 ms, 0 missing |

The per-device thresholds are in `config.yaml`. The testbed is frozen as git tag `testbed-v1`.

### Step 23 — Overnight collection (`collect_sessions.sh`)
| Command | Expected |
|---|---|
| `cat data/collect.log` | One start and one end line per session, exit code 0 |
| `for d in data/raw/session_0*; do python3 -m experiments.check_session $d \| grep -E "session_\|wrong\|WARNING\|MISSING"; done` | `complete=True`, `dirty=False`, the same commit, 0 wrong rows |

While a collection runs: keep the dashboards closed, keep the machine awake, and change
nothing in `topo/` or `experiments/`.

## Notes for the paper

- Loss means no ping reply within 1 s. Under overload it mostly reflects queueing delay above 1 s.
- Fault magnitudes were calibrated in a pilot so that decoys produce device-level symptoms
  while the shared link stays below capacity.
- Seeds fix the sequence of events, not exact timing: the same seed gave flood lengths of 58 s
  and 41 s in two runs.
- Degradation thresholds come from normal-only sessions, per device.