# topo/ — The smart-home IoT network

Emulated smart-home network for **Trust-Aware Agentic AI for Smart-Home IoT Network Management**.
Ten IoT devices share one home switch, one Linux router and one 10 Mbit/s uplink to a cloud host.
The folder generates realistic, seeded IoT traffic (MQTT sensors, UDP media, TCP bulk, a TV
stream), measures every device at three layers every 2 s, and injects labelled events:
congestion (where rate-limiting helps) and decoy faults (where it cannot).

## Files

| File | Role |
|---|---|
| `__init__.py` | Makes `topo/` importable from other folders |
| `smart_home_topo.py` | Builds the network; starts/stops all services; interactive `mininet>` prompt with custom commands; port map |
| `mqtt_traffic.py` | Mosquitto broker on the cloud, recording subscriber, MQTT sensors (seq + ts in every message) |
| `normal_traffic.py` | iperf (v2) receivers on the cloud; UDP media bursts, TCP bursts, TV stream |
| `network_monitor.py` | Per-device throughput, RTT, jitter, loss; both router sides; TCP internals |
| `mqtt_delay.py` | Per-sensor MQTT delivery report (delay, missing, duplicates) — run in a second terminal |
| `congestion.py` | Labelled congestion events (C_SEVERE, C_BORDER) from allowed devices only |
| `faults.py` | Labelled decoy faults (F_WAN, F_DEVLINK) that rate-limiting cannot fix |

## Requirements

```bash
apt install -y mininet openvswitch-switch iperf tcpdump mosquitto mosquitto-clients
systemctl enable --now openvswitch-switch
systemctl disable --now mosquitto      # our broker runs inside the cloud host
```

Use **iperf version 2**, not iperf3 (iperf3 serves one client at a time).

## Run

From the project root:

```bash
cd /home/beast1/Documents/research/Trust-Aware-Agentic-AI
sudo mn -c
sudo python3 topo/smart_home_topo.py                 # seed 42, packet capture on
sudo python3 topo/smart_home_topo.py --seed 43 --no-pcap
```

Second terminal (no sudo): `python3 topo/mqtt_delay.py` or `watch -n 5 python3 topo/mqtt_delay.py`.

### Commands at the `mininet>` prompt

| Command | Effect |
|---|---|
| `<device> <cmd>` | Run a Linux command inside a device, e.g. `lock ping -c 3 172.16.0.11` |
| `sh <cmd>` | Run a command on the Kali machine |
| `congest [severe\|border]` | Start a random labelled congestion event |
| `stopflood` | End a running congestion event early |
| `fault [wan\|devlink]` | Start a random labelled decoy fault |
| `stopfault` | End a running fault early (cable restored) |
| `exit` | Stop everything cleanly |

Events never overlap: a new event is refused while one is running.

### Use from other folders

```python
from topo.smart_home_topo import DEVICES, build_network, start_services, stop_services
net, hosts, cloud, router = build_network()
net.start()
start_services(net, hosts, cloud, router, seed=42, pcap=False)
...
stop_services(hosts, cloud, router, pcap=False)
net.stop()
```

## Topology

```
 IoT devices --[10 Mbit, 5 ms]-- s1 --[10 Mbit, 5 ms]-- ROUTER --[10 Mbit, 10 ms]-- s2 --[10 Mbit, 10 ms]-- cloud
             home LAN 10.0.0.x/24                     r-eth0 .254 | r-eth1 .1      WAN 172.16.0.x/24
```

| Device | IP | Device | IP |
|---|---|---|---|
| camera | 10.0.0.1 | light | 10.0.0.6 |
| doorbell | 10.0.0.2 | plug | 10.0.0.7 |
| lock | 10.0.0.3 | phone | 10.0.0.8 |
| thermostat | 10.0.0.4 | tv | 10.0.0.9 |
| speaker | 10.0.0.5 | laptop | 10.0.0.10 |
| router | 10.0.0.254 (r-eth0), 172.16.0.1 (r-eth1) | cloud | 172.16.0.11 |

| Link | Bandwidth | Delay | Loss |
|---|---|---|---|
| device – s1 | 10 Mbit/s | 5 ms | 0 % |
| router – s1 | 10 Mbit/s | 5 ms | 0 % |
| router – s2 | 10 Mbit/s | 10 ms | 0 % |
| s2 – cloud | 10 Mbit/s | 10 ms | 0 % |

Baseline RTT: ≈ 20 ms inside the home, ≈ 60 ms device → cloud.
**Why these values:** a deliberate experimental choice, not a typical ISP plan — a few devices can
reliably saturate 10 Mbit/s while normal traffic stays well below it; Mininet stays accurate at
tens of Mbit/s (Handigol et al., CoNEXT 2012); `loss=0` means every measured loss is caused by
congestion or a labelled fault.

## Normal traffic (seeded)

| Device | Protocol | Every | Size | Cap / QoS |
|---|---|---|---|---|
| thermostat | MQTT | 20–40 s | `temp=..` | QoS 0 |
| lock | MQTT | 120–300 s | `state=locked;battery=..` | QoS 1 |
| doorbell | MQTT | 60–180 s | `event=motion` | QoS 1 |
| light | MQTT | 300–600 s | `on=..;brightness=..` | QoS 0 |
| plug | MQTT | 300–600 s | `on=1;power_w=..` | QoS 0 |
| camera | UDP | 20–60 s | 100–400 KB | 2 Mbit/s |
| speaker | UDP | 15–45 s | 30–200 KB | 1 Mbit/s |
| phone | TCP | 5–30 s | 100–1000 KB | 2 Mbit/s |
| laptop | TCP | 5–20 s | 200–2000 KB | 3 Mbit/s |
| tv | TCP | continuous | stream | 2 Mbit/s |

MQTT messages carry `seq=<n>;ts=<send time>;...`. Each device's bash loop is seeded with
`RANDOM=device_seed(seed, name)` where `device_seed = seed*1000 + sum(ord(c) for c in name)`.
Same seed → same sequence of sizes, waits and payloads (not bit-identical timing).

**Average offered load ≈ 2.8 Mbit/s on a 10 Mbit/s link** (tv 2.00, laptop ≈ 0.55, phone ≈ 0.21,
camera + speaker ≈ 0.07, MQTT ≈ 0) — normal traffic stays well below capacity.

## Measurements (every 2 s)

| Layer | Values | Log |
|---|---|---|
| Network | rx/tx kbit/s, RTT, jitter (ping mdev), loss (3 pings, decimals kept) | `/tmp/network_metrics/<device>.log` |
| Shared link | router home side (rx = all home uploads), internet side (tx = what leaves) | `/tmp/network_metrics/router_lan.log`, `router_wan.log` |
| Transport | conns, cwnd, ssthresh, srtt, retrans_total, unacked (phone, laptop, tv) | `/tmp/tcp_metrics/<device>.log` |
| Application | MQTT delivery delay, missing, duplicates | `/tmp/mqtt_received.log` (+ `mqtt_delay.py`) |
| Raw packets | everything on both router sides | `captures/*.pcap` |

Ping runs in the background *during* each 2 s window, and throughput divides by the measured
window length. A ping reply slower than 1 s counts as lost.

## Events (ground truth)

| Type | Cause | Who suffers | Shared link | Rate-limiting helps? | should_act |
|---|---|---|---|---|---|
| C_SEVERE | 2–3 of laptop/phone/tv at 8–20 Mbit/s each | everyone | full | yes | yes |
| C_BORDER | 1 of laptop/phone/tv at 6–12 Mbit/s | sometimes | 7–10 Mbit/s | often | yes |
| F_WAN | WAN cable delay 30–80 ms, loss 1–5 % | everyone | **not** full | no | no |
| F_DEVLINK | one IoT device's cable loss 5–20 % | that device only | normal | no | no |

Durations 15–60 s. Only laptop, phone and tv may flood; protected devices (camera, lock,
doorbell, thermostat, speaker, light, plug) never do. Every event writes a `start` and an
`end` line with real times.

## Log files

| File | Contents |
|---|---|
| `/tmp/normal_traffic.log` | Every traffic event SENT: `time,device,protocol,size,kind` |
| `/tmp/mqtt_received.log` | Every MQTT message DELIVERED: `arrival_time,topic,payload` |
| `/tmp/iperf_udp_server.log` | One CSV line per UDP burst (bytes, rate, jitter, lost, total, loss %) |
| `/tmp/iperf_tcp_server.log` | One CSV line per finished TCP transfer |
| `/tmp/network_metrics/*.log` | `timestamp,device,rx_kbps,tx_kbps,rtt_ms,jitter_ms,loss_pct` |
| `/tmp/tcp_metrics/*.log` | `timestamp,device,conns,cwnd,ssthresh,srtt_ms,retrans_total,unacked` |
| `/tmp/events.log` | `timestamp,event_id,event_type,device,params,duration_s,phase` |
| `/tmp/port_map.json` | IoT device → s1 port, e.g. `{"laptop": "s1-eth10"}` |

Start order: capture → MQTT → iperf → monitoring → event logs → port map.
Stop order: events → monitoring → iperf → MQTT → capture → network.

---

## Build log

### Step 1 — Home LAN (10 IoT devices + s1)
| Command | Expected |
|---|---|
| `nodes` | 10 devices + s1 |
| `lock ifconfig` | 10.0.0.3 |
| `pingall` | 0 % dropped (90/90) |

### Step 2 — The router
`LinuxRouter` turns on `net.ipv4.ip_forward`; devices use `default via 10.0.0.254`.
| Command | Expected |
|---|---|
| `router sysctl net.ipv4.ip_forward` | = 1 |
| `lock ip route` | default via 10.0.0.254 |
| `pingall` | 0 % dropped (110/110) |

### Step 3 — WAN switch s2 and cloud
| Command | Expected |
|---|---|
| `router ip addr` | 10.0.0.254 and 172.16.0.1 |
| `lock ping -c 3 172.16.0.11` | reaches the cloud |
| `pingall` | 0 % dropped (132/132) |

Mini experiment: `router sysctl -w net.ipv4.ip_forward=0` → `lock ping -c 3 172.16.0.11` fails;
set it back to 1 → works.

### Step 4 — Realistic cables
| Command | Expected |
|---|---|
| `lock ping -c 4 10.0.0.254` | ≈ 20 ms |
| `lock ping -c 4 172.16.0.11` | ≈ 60 ms |
| `iperf laptop cloud` | ≈ 9–9.5 Mbit/s |

Mini experiment (first IoT victim):
```
mininet> cloud iperf -s > /dev/null &
mininet> laptop iperf -c 172.16.0.11 -t 20 > /dev/null &
mininet> lock ping -c 10 172.16.0.11        # RTT far above 60 ms
mininet> cloud kill %iperf
```

### Step 5 — Packet capture
| Command | Expected |
|---|---|
| `sh ls -lh captures` | lan_*.pcap, wan_*.pcap |
| `sh tcpdump -n -r captures/lan_XXXX.pcap` | 10.0.0.3 > 172.16.0.11 ICMP |

Mini experiment: `tcpdump -n -e` on both files — same IPs, different MACs (router swaps them).

### Step 6–7 — MQTT broker and sensors
| Command | Expected |
|---|---|
| `cloud ss -ltn` | :1883 |
| after ~10 s `sh cat /tmp/mqtt_received.log` | five `home/<sensor>/telemetry` topics |
| `sh cut -d, -f2 /tmp/normal_traffic.log \| sort \| uniq -c` vs same on `mqtt_received.log` | same counts (100 % delivery) |

QoS 0 sensors tend to lose messages under congestion; QoS 1 sensors get delayed (retries).

### Step 8–9 — Media, heavy devices, TV stream
| Command | Expected |
|---|---|
| `cloud ss -lun` / `cloud ss -ltn` | UDP :5001 / TCP :1883 and :5001 |
| `tv ss -tn` | one ESTAB connection to 172.16.0.11:5001 |
| `sh cat /tmp/iperf_udp_server.log` | one line per burst, jitter < 1 ms, 0 lost |
| router upload over 10 s | ≈ 2,000–4,000 kbps |

```
mininet> router A=$(cat /sys/class/net/r-eth0/statistics/rx_bytes); sleep 10; B=$(cat /sys/class/net/r-eth0/statistics/rx_bytes); echo $(( (B-A)*8/10000 )) kbps
```

### Step 10 — Random sizes, reproducible seed
| Command | Expected |
|---|---|
| start-up | `(seed=42)` in both traffic lines |
| `sh grep laptop /tmp/normal_traffic.log \| cut -d, -f4 \| head -3` | same 3 sizes in two runs with the same seed |

### Step 11–12 — Throughput, RTT, jitter, loss
| Command | Expected |
|---|---|
| `sh ls /tmp/network_metrics` | 12 `.log` files |
| `sh column -s, -t < /tmp/network_metrics/camera.log \| tail -5` | rtt ≈ 60, jitter < 1, loss 0 |
| `sh column -s, -t < /tmp/network_metrics/router_lan.log \| tail -5` | rx ≈ 2000–4000; ping columns NA |
| `sh tail -4 /tmp/network_metrics/tv.log \| cut -d, -f1` | rows ≈ 2 s apart |

During a flood, the lock (≈ 0 kbps) shows RTT in the hundreds of ms and loss such as 33.3333
(never 3333), while router_lan rx ≈ 10,000.

Normal operation also contains short blips (microbursts from TCP, 1-of-3 ping lost). They are
real, expected, and are why degradation thresholds come from normal-only data, not fixed values.

### Step 13 — TCP internals
| Command | Expected |
|---|---|
| `sh ls /tmp/tcp_metrics` | laptop.log phone.log tv.log |
| `sh column -s, -t < /tmp/tcp_metrics/tv.log \| tail -5` | conns 1, srtt ≈ 60–65, retrans small |

During a flood the TV's srtt rises, retrans_total climbs, cwnd drops — often at the same time as or
before the throughput drop (early warning).

### Step 14 — MQTT delivery delay
| Command | Expected |
|---|---|
| `python3 topo/mqtt_delay.py` | five sensors, MISSING 0, DUPS 0, AVG ≈ 150–200 ms |

≈ 150–200 ms baseline because each `mosquitto_pub` opens a new connection (TCP handshake +
MQTT connect + publish), like a battery-powered sensor. One-way delay relies on all hosts
sharing one clock.

### Step 15 — Labelled congestion
| Command | Expected |
|---|---|
| `congest severe` | event printed; start lines in `/tmp/events.log` |
| `congest` during an event | refused (no overlap) |
| `stopflood` | end line written early |
| `sh grep -cE ',(camera\|lock\|doorbell\|thermostat\|speaker\|light\|plug),' /tmp/events.log` | 0 |

### Step 16 — Decoy faults
| Command | Expected |
|---|---|
| `fault wan` then `router tc qdisc show dev r-eth1` | delay 30–80 ms, loss 1–5 % |
| after the event | back to delay 10 ms, no loss |
| `fault devlink` | loss only on that one device |

Mini experiment (same symptom, different cause): during `congest severe` the lock's RTT is high
and router_lan rx ≈ 10,000; during `fault wan` the lock's RTT is high but router_lan rx stays
≈ 2,000–4,000 — limiting the laptop would not help.

### Step 17 — Reusable package and port map
| Command | Expected |
|---|---|
| `sh cat /tmp/port_map.json` | 10 entries, e.g. `"laptop": "s1-eth10"` |
| `sudo python3 -c "from topo.smart_home_topo import DEVICES; print(len(DEVICES))"` | 10 |
| `--seed 43 --no-pcap` | seed 43, no capture |

Mini experiment (preview of the only mitigation): `ovs-vsctl set interface <laptop port>
ingress_policing_rate=2000 ingress_policing_burst=200` → laptop iperf ≈ 2 Mbit/s; set both to 0 →
≈ 9 Mbit/s again.

## Notes for the paper

- Link values are an experimental choice; add a sensitivity check at bw = 20 and 50.
- iperf version 2, not iperf3.
- Average-load table (≈ 2.8 of 10 Mbit/s) shows normal traffic stays below capacity.
- Seeds make runs repeatable in sequence, not bit-identical.
- MQTT one-way delay relies on a shared clock; real devices would need NTP/PTP.
- A ping reply > 1 s counts as lost; loss resolution is 33.3 % per row (3 pings).
- Decoy faults (F_WAN, F_DEVLINK) are the cases where acting cannot help.