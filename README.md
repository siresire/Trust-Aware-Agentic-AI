# Trust-Aware Agentic AI for Smart-Home IoT Network Management

A Mininet smart-home IoT testbed for studying when an AI agent should (and should not)
act on network-performance predictions, based on prediction confidence, device importance,
and homeowner policy.

## Problem

Smart-home IoT devices (cameras, locks, doorbells, sensors, speakers, phones, TVs, laptops)
share one home network and one internet uplink, so traffic from one device can degrade
others. A model can predict this degradation, but acting on every prediction is unsafe:
the action may hit an important device, break a homeowner rule, or not fix the problem.
This project builds a trust-aware agent that acts only when the prediction is confident,
the affected device matters, and the policy allows modifying the target device.



## Topology

```
 IoT devices --[10 Mbit, 5 ms]-- s1 --[10 Mbit, 5 ms]-- ROUTER --[10 Mbit, 10 ms]-- s2 --[10 Mbit, 10 ms]-- cloud
             home LAN 10.0.0.x/24                     r-eth0 .254 | r-eth1 .1      WAN 172.16.0.x/24
```

| Device     | IP           | Device | IP           |
|------------|--------------|--------|--------------|
| camera     | 10.0.0.1     | light  | 10.0.0.6     |
| doorbell   | 10.0.0.2     | plug   | 10.0.0.7     |
| lock       | 10.0.0.3     | phone  | 10.0.0.8     |
| thermostat | 10.0.0.4     | tv     | 10.0.0.9     |
| speaker    | 10.0.0.5     | laptop | 10.0.0.10    |
| router     | 10.0.0.254 (r-eth0), 172.16.0.1 (r-eth1) | cloud | 172.16.0.11 |

| Link           | Bandwidth | Delay | Loss |
|----------------|-----------|-------|------|
| device – s1    | 10 Mbit/s | 5 ms  | 0 %  |
| router – s1    | 10 Mbit/s | 5 ms  | 0 %  |
| router – s2    | 10 Mbit/s | 10 ms | 0 %  |
| s2 – cloud     | 10 Mbit/s | 10 ms | 0 %  |

---


### Step 1: Home LAN (10 IoT devices + switch s1)
All devices on 10.0.0.x/24, connected through the standalone OVS switch `s1`.

**Check it**

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

**Check it**

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

**Check it**

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

**Check it**

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

One device fills the shared link, and a different, innocent IoT device suffers.

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