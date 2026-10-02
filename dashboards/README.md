# dashboards/ — Live terminal viewers (read-only)

Two viewers that read the logs `topo/` writes while the network runs. They need no sudo and
change nothing. Keep them closed during dataset sessions, because each redraw re-reads every
log on the same machine that emulates the network.

## Files

| File | Shows |
|---|---|
| `__init__.py` | Makes `dashboards/` a package |
| `network_dashboard.py` | The effect: how each IoT device feels, the shared uplink, the running event |
| `monitor.py` | The cause: who sends what, MQTT delivery, event START/END lines |

## Run

From the project root, each in its own terminal, while the network runs:

```bash
python3 -m dashboards.network_dashboard
python3 -m dashboards.monitor
```

Both accept `--once` (print one frame and exit) and `--no-color`.

## Status rules (`network_dashboard.py`)

| Status | Per 2-second sample | Shown when |
|---|---|---|
| OK | RTT ≤ 1.5 × baseline, no loss | – |
| WARN | RTT > 1.5 × baseline or any loss | all of the last 3 samples are at least WARN |
| CRIT | RTT > 3 × baseline, loss ≥ 66 %, or no reply | all of the last 3 samples are CRIT |
| LEARNING | – | fewer than 10 quiet samples so far |
| STALE | – | no new row for more than 8 s |

The baseline is the device's median RTT outside events and the 30 s after them. These rules
are for viewing only. The dataset labels use the thresholds in `config.yaml`.

## Flag rule (`monitor.py`)

`SUSTAINED HIGH` appears when a device's 10-second average TX is above 0.8 × its rate cap
(1.3 × for the TV stream). `SENT` and `KB` come from the sent log (normal traffic only);
`TX avg` is measured on the card and includes floods.

## Build log

### Step 19 — Network dashboard
| When | Expected |
|---|---|
| First 20 s | `LEARNING` on every device |
| Normal traffic | `OK`, baseline about 64–67 ms, uplink bar green |
| `congest severe` | Uplink red; flooders marked `flooding`; protected devices WARN/CRIT; `should act: YES` |
| `fault wan` | Devices WARN, uplink stays green; `should act: NO (decoy)` |
| `fault devlink` | One device WARN/CRIT with `fault on its link` |
| Network stopped | `STALE` after about 8 s |

### Step 20 — Traffic and events monitor
| When | Expected |
|---|---|
| Normal traffic | Coloured feed (MQTT, UDP, TCP); no flags; MQTT `MISSING` 0 |
| `congest severe` | Red START lines; flooders `SUSTAINED HIGH`; MQTT `LAST` far above the median |
| `fault wan` | Magenta START line; nobody flagged |

A symptom on the network dashboard with no cause on the monitor is the signature of a decoy.