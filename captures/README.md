# captures/ — Packet captures

Written automatically by `topo/smart_home_topo.py`

| File | Contents |
|---|---|
| `lan_<YYYYmmdd_HHMMSS>.pcap` | Every packet on the router's home side (`r-eth0`) |
| `wan_<YYYYmmdd_HHMMSS>.pcap` | Every packet on the router's internet side (`r-eth1`) |
| `tcpdump_lan.log`, `tcpdump_wan.log` | tcpdump's own start-up messages |

Read a capture:

    tcpdump -n -r captures/lan_XXXX.pcap | head

Open in Wireshark as a normal user (after `chown -R beast1:beast1 captures`).