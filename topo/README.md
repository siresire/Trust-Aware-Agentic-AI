# topo/ — The smart-home IoT network

This folder builds and runs the emulated smart-home network used by the
Trust-Aware Agentic AI project: 10 IoT devices, a home switch, a Linux router,
a WAN switch and a cloud host, with shaped links and packet capture.

## Files

| File | Role |
|---|---|
| `smart_home_topo.py` | Builds the network, starts packet capture and traffic, opens the `mininet>` prompt |
| `mqtt_traffic.py` | MQTT broker (Mosquitto) on the cloud, recording subscriber, IoT sensor publishers |

## Requirements

```bash
apt install -y mininet openvswitch-switch iperf tcpdump mosquitto mosquitto-clients
systemctl enable --now openvswitch-switch
systemctl disable --now mosquitto      # our broker runs inside the cloud host instead
```

## Run

Always from the project root:

```bash
cd /home/beast1/Documents/research/Trust-Aware-Agentic-AI
sudo mn -c                          # clean up anything left from a previous run
sudo python3 topo/smart_home_topo.py
```

Inside the `mininet>` prompt: `<device> <command>` runs a command inside a device,
`sh <command>` runs it on the Kali machine, `exit` shuts everything down.

## Topology

```
 IoT devices --[10 Mbit, 5 ms]-- s1 --[10 Mbit, 5 ms]-- ROUTER --[10 Mbit, 10 ms]-- s2 --[10 Mbit, 10 ms]-- cloud
             home LAN 10.0.0.x/24                     r-eth0 .254 | r-eth1 .1      WAN 172.16.0.x/24
```

| Device     | IP        | Device | IP        |
|------------|-----------|--------|-----------|
| camera     | 10.0.0.1  | light  | 10.0.0.6  |
| doorbell   | 10.0.0.2  | plug   | 10.0.0.7  |
| lock       | 10.0.0.3  | phone  | 10.0.0.8  |
| thermostat | 10.0.0.4  | tv     | 10.0.0.9  |
| speaker    | 10.0.0.5  | laptop | 10.0.0.10 |
| router     | 10.0.0.254 (r-eth0), 172.16.0.1 (r-eth1) | cloud | 172.16.0.11 |

| Link        | Bandwidth | Delay | Loss |
|-------------|-----------|-------|------|
| device – s1 | 10 Mbit/s | 5 ms  | 0 %  |
| router – s1 | 10 Mbit/s | 5 ms  | 0 %  |
| router – s2 | 10 Mbit/s | 10 ms | 0 %  |
| s2 – cloud  | 10 Mbit/s | 10 ms | 0 %  |

---

## Log files (written during a run)

| File | Written by | Contents |
|---|---|---|
| `/tmp/normal_traffic.log` | device traffic loops | Every traffic event SENT: `time,device,protocol,size,kind` |
| `/tmp/mqtt_received.log` | subscriber on cloud | Every MQTT message DELIVERED: `arrival_time,topic,payload` |

## Build log

### Step 1: Home LAN (10 IoT devices + switch s1)
All devices on 10.0.0.x/24, connected through the standalone OVS switch `s1`.

| Command | What to check |
|---|---|
| `nodes` | Ten devices plus `s1` |
| `net` | Each device has one cable (`-eth0`) to s1 |
| `lock ifconfig` | IP is `10.0.0.3` |
| `camera ping -c 3 laptop` | Two home devices talk through s1, 0 % loss |
| `pingall` | `0% dropped (90/90 received)` |

### Step 2: The router
`LinuxRouter` = a Mininet host with IP forwarding on (`net.ipv4.ip_forward=1`).
Home side `r-eth0` = 10.0.0.254. Every device has `default via 10.0.0.254`.

| Command | What to check |
|---|---|
| `router ip addr show r-eth0` | `inet 10.0.0.254/24` |
| `router sysctl net.ipv4.ip_forward` | `= 1` |
| `lock ip route` | `default via 10.0.0.254` |
| `lock ping -c 3 10.0.0.254` | Lock reaches the router |
| `pingall` | `0% dropped (110/110 received)` |

### Step 3: WAN switch s2 and cloud
Second subnet 172.16.0.x/24. Router WAN side `r-eth1` = 172.16.0.1; cloud = 172.16.0.11,
`default via 172.16.0.1`.

| Command | What to check |
|---|---|
| `router ip addr` | Two IPs: 10.0.0.254 and 172.16.0.1 |
| `cloud ip route` | `default via 172.16.0.1` |
| `lock ping -c 3 172.16.0.11` | Lock reaches the cloud through the router |
| `lock tracepath -n 172.16.0.11` | Via 10.0.0.254, then 172.16.0.11 |
| `pingall` | `0% dropped (132/132 received)` |

**Mini experiment: the router does the work**

```
mininet> router sysctl -w net.ipv4.ip_forward=0
mininet> lock ping -c 3 172.16.0.11        # fails
mininet> router sysctl -w net.ipv4.ip_forward=1
mininet> lock ping -c 3 172.16.0.11        # works again
```

### Step 4: Realistic cables (bandwidth, delay, loss)
`TCLink` enforces `bw`, `delay` and `loss` with Linux `tc`. At start-up each cable prints
`(10.00Mbit 5ms delay 0.00000% loss)`, which confirms the shaping is on.

| Command | What to check |
|---|---|
| `lock ping -c 4 10.0.0.254` | About 20 ms |
| `lock ping -c 4 10.0.0.10` | About 20 ms |
| `lock ping -c 4 172.16.0.11` | About 60 ms |
| `iperf laptop cloud` | About 9 to 9.5 Mbit/s, just under the 10 Mbit limit |
| `pingall` | Still `0% dropped (132/132 received)` |

- The first ping of each run can be slower because of ARP (looking up the next device's MAC address).
- iperf lands a little below 10 because of packet headers and TCP overhead: the difference
  between bandwidth and throughput.

**Mini experiment: your first IoT victim**

```
mininet> cloud iperf -s > /dev/null &
mininet> lock ping -c 5 172.16.0.11                    # before: ~60 ms
mininet> laptop iperf -c 172.16.0.11 -t 20 > /dev/null &
mininet> lock ping -c 10 172.16.0.11                   # during: RTT jumps far above 60 ms
mininet> cloud kill %iperf
```

| Line | Meaning |
|---|---|
| `cloud iperf -s ... &` | A receiver on the cloud, running in the background |
| `laptop iperf -c ... -t 20` | The laptop uploads as fast as it can for 20 s, filling the 10 Mbit link |
| `lock ping` during the upload | The lock sent almost nothing, yet its delay rises: its packets wait in a queue behind the laptop's |
| `cloud kill %iperf` | Stop the receiver |

**Why these link values:** a deliberate experimental choice, not a typical ISP plan.
A few devices can reliably saturate 10 Mbit/s while normal IoT traffic stays well below it,
Mininet stays accurate at tens of Mbit/s (Handigol et al., CoNEXT 2012), and `loss=0`
means every measured loss comes from real congestion.

### Step 5: Packet capture (tcpdump)
Two tcpdump processes on the router record every packet on the home side (`r-eth0`) and the
internet side (`r-eth1`) into `captures/lan_<time>.pcap` and `captures/wan_<time>.pcap`.
They start right after `net.start()` and are stopped with SIGINT before `net.stop()`.

| Command | What to check |
|---|---|
| `lock ping -c 3 172.16.0.11` | Makes some traffic to capture |
| `sh ls -lh captures` | `lan_XXXX.pcap`, `wan_XXXX.pcap`, sizes above 0 |
| `sh tcpdump -n -r captures/lan_XXXX.pcap` | `10.0.0.3 > 172.16.0.11: ICMP echo request` and replies |
| `sh tcpdump -n -r captures/wan_XXXX.pcap` | The same pings on the outside side |
| `exit` | `Stopping packet capture` before `Stopping network` |

After exiting: `chown -R beast1:beast1 captures` to open the files in Wireshark.

**Mini experiment: what the router changes**

```
mininet> lock ping -c 1 172.16.0.11
mininet> sh tcpdump -n -e -r captures/lan_XXXX.pcap icmp | tail -2
mininet> sh tcpdump -n -e -r captures/wan_XXXX.pcap icmp | tail -2
```

Same IP addresses in both files (IP is end to end); different MAC addresses (MAC is one hop,
and the router swaps them).

### Step 6: MQTT broker and one sensor (`mqtt_traffic.py`)
Mosquitto runs on the cloud (port 1883, anonymous). A subscriber on `home/#` records every
delivered message to `/tmp/mqtt_received.log`. The thermostat publishes `temp=<18..25>` to
`home/thermostat/telemetry` with QoS 1 every 20–40 s and logs each send to
`/tmp/normal_traffic.log`. Traffic starts after packet capture and stops before it.

| Command | What to check |
|---|---|
| `cloud ss -ltn` | `0.0.0.0:1883` listening |
| `lock mosquitto_pub -h 172.16.0.11 -t home/test -m hello` | Test message sent |
| `sh cat /tmp/mqtt_received.log` | `...,home/test,hello` |
| after ~1 min: `sh cat /tmp/normal_traffic.log` | `thermostat,mqtt,7B,burst` lines (sent) |
| `sh cat /tmp/mqtt_received.log` | `home/thermostat/telemetry,temp=..` lines (arrived) |
| `sh tcpdump -n -r captures/wan_XXXX.pcap port 1883 \| head -20` | MQTT packets 10.0.0.4 → 172.16.0.11.1883 |

**Mini experiment: application-level delay**

```
mininet> sh tail -1 /tmp/normal_traffic.log
mininet> sh tail -1 /tmp/mqtt_received.log
```

Arrival time minus sent time ≈ 0.15–0.2 s: TCP handshake + MQTT connect + publish,
because each `mosquitto_pub` opens a new connection (like a battery-powered sensor).