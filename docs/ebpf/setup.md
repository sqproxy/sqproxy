# eBPF Setup Guide

Step-by-step guide to configure eBPF packet redirection for Source Query Proxy.

## Prerequisites

Before setting up eBPF, ensure you have:

- ✅ Linux kernel 4.4+ (check with `uname -r`)
- ✅ BCC installed (see [Installation Guide](../installation.md))
- ✅ Root access or CAP_BPF/CAP_SYS_ADMIN capability
- ✅ Network interface name (use `ip addr show`)

## Quick Setup

### 1. Enable eBPF in Configuration

Create `/etc/sqproxy/conf.d/00-globals.yaml`:

```yaml
ebpf:
  enabled: true
  interface: eth0  # Your network interface name
```

### 2. Run sqproxy

```bash
sudo sqproxy run
```

That's it! eBPF redirection is now active.

## Detailed Configuration

### Find Your Network Interface

```bash
# Method 1: ip command
ip addr show

# Method 2: ifconfig
ifconfig

# Method 3: List all interfaces
ls /sys/class/net/

# Common interface names:
# - eth0, eth1 (Ethernet)
# - ens3, ens18 (predictable naming)
# - enp0s3 (PCI-based naming)
# - wlan0 (Wi-Fi)
```

### Configure eBPF Settings

```yaml
# /etc/sqproxy/conf.d/00-globals.yaml
ebpf:
  # Enable eBPF packet redirection
  enabled: true

  # Network interface to attach eBPF programs
  interface: eth0

  # Optional: Disable redirection (debug mode)
  no_redirect: false
```

### Configure Server Mappings

```yaml
# /etc/sqproxy/conf.d/10-servers.yaml
servers:
  csgo-main:
    network:
      server_ip: "192.168.1.100"
      server_port: 27015  # Game server port
      bind_port: 27016    # sqproxy port
```

## Verification

### 1. Check sqproxy Logs

```bash
sudo sqproxy run

# Expected output:
# INFO: Starting Source Query Proxy v3.0.0
# INFO: Loading configuration from /etc/sqproxy/conf.d
# INFO: Loaded 1 server(s): csgo-main
# INFO: Starting eBPF redirection on interface eth0
# INFO: Compiling BPF program...
# INFO: BPF program compiled successfully (3456 bytes)
# INFO: Loading BPF functions...
# INFO: ✓ tc_ingress loaded
# INFO: ✓ tc_egress loaded
# INFO: Attaching to traffic control...
# INFO: ✓ Attached ingress filter
# INFO: ✓ Attached egress filter
# INFO: eBPF redirection started successfully
# INFO: Proxy ready, listening on 192.168.1.100:27016
```

### 2. Verify tc Attachment

```bash
# Show ingress filters
sudo tc filter show dev eth0 ingress

# Expected output:
# filter protocol ip pref 49152 bpf chain 0
# filter protocol ip pref 49152 bpf chain 0 handle 0x1 bpf:[tc_ingress]

# Show egress filters
sudo tc filter show dev eth0 egress

# Expected output similar to above
```

### 3. List BPF Programs

```bash
# List all loaded BPF programs
sudo bpftool prog list | grep sqproxy

# Show BPF maps
sudo bpftool map list
```

### 4. Test Redirection

From another machine:

```bash
# Query the server (should be redirected to sqproxy)
nmap -sU -p 27015 -Pn --script=a2s-info 192.168.1.100

# Or use valve-server-query
valve-server-query 192.168.1.100:27015 info
```

Watch sqproxy logs - you should see the query being handled.

## Advanced Configuration

### Multiple Network Interfaces

If you have multiple interfaces and want specific behavior:

```yaml
# Use specific interface
ebpf:
  enabled: true
  interface: ens3  # Public interface

# Servers will be accessible via this interface
```

### Per-Server eBPF Control

Disable redirection for specific servers:

```yaml
servers:
  # Normal server with eBPF
  csgo-prod:
    network:
      server_port: 27015
      bind_port: 27016

  # Debug server without eBPF
  csgo-debug:
    network:
      server_port: 27017
      bind_port: 27018
      ebpf_no_redirect: true  # Disable for this server
```

### IP-Based Redirection

For multi-IP setups, use IP+port mapping:

```yaml
servers:
  server-1:
    network:
      server_ip: "192.168.1.100"
      bind_ip: "192.168.1.100"
      server_port: 27015
      bind_port: 27016

  server-2:
    network:
      server_ip: "192.168.1.101"
      bind_ip: "192.168.1.101"
      server_port: 27015
      bind_port: 27016
```

## Running as Service

### systemd Service

Create `/etc/systemd/system/sqproxy.service`:

```ini
[Unit]
Description=Source Query Proxy with eBPF
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/etc/sqproxy
ExecStart=/usr/local/bin/sqproxy run
Restart=on-failure
RestartSec=10s

# Security (while keeping eBPF capabilities)
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable sqproxy
sudo systemctl start sqproxy
sudo systemctl status sqproxy
```

### Non-Root Running (Advanced)

Grant capabilities to Python binary:

```bash
# For kernel 5.8+
sudo setcap cap_bpf,cap_net_admin=ep $(which python3)

# For older kernels
sudo setcap cap_sys_admin,cap_net_admin=ep $(which python3)

# Now you can run without sudo
sqproxy run
```

!!! warning "Security Consideration"
    Granting capabilities to python3 affects all Python scripts. Consider using a virtual environment with a dedicated Python interpreter.

### Using Virtual Environment

```bash
# Create venv
python3 -m venv /opt/sqproxy-venv
source /opt/sqproxy-venv/bin/activate

# Install sqproxy
pip install source-query-proxy

# Grant capabilities to venv python
sudo setcap cap_bpf,cap_net_admin=ep /opt/sqproxy-venv/bin/python3

# Run
/opt/sqproxy-venv/bin/sqproxy run
```

## Monitoring

### Watch eBPF Statistics

```bash
# Monitor tc statistics
watch -n 1 'tc -s filter show dev eth0 ingress'

# Monitor BPF map entries
watch -n 1 'sudo bpftool map dump name port_map'
```

### View Packet Redirection

```bash
# Capture packets on bind_port (should see A2S queries)
sudo tcpdump -i eth0 'udp port 27016' -n -vv

# Capture packets on server_port (should NOT see A2S queries)
sudo tcpdump -i eth0 'udp port 27015' -n -vv
```

### sqproxy Logging

```bash
# Follow logs in real-time
sudo journalctl -u sqproxy -f

# Show recent errors
sudo journalctl -u sqproxy -p err -n 50

# Show logs with timestamps
sudo journalctl -u sqproxy --since "1 hour ago"
```

## Debugging

### Enable Debug Logging

```bash
export SQPROXY_LOGLEVEL=DEBUG
sudo -E sqproxy run
```

### Check BPF Program

```bash
# Dump generated BPF C code (for debugging)
# This requires adding debug output to sqproxy code

# Show BPF program info
sudo bpftool prog show

# Show BPF map contents
sudo bpftool map dump name port_map
sudo bpftool map dump name addr_map
```

### Test Without eBPF

Temporarily disable eBPF to isolate issues:

```yaml
ebpf:
  enabled: false
```

Run sqproxy and test if it responds to queries (without redirection).

## Cleanup

### Stop eBPF Redirection

```bash
# Stop sqproxy
sudo systemctl stop sqproxy

# OR send SIGTERM
sudo pkill -TERM sqproxy
```

sqproxy automatically cleans up eBPF programs on shutdown.

### Manual Cleanup (if needed)

```bash
# Remove tc filters
sudo tc filter del dev eth0 ingress
sudo tc filter del dev eth0 egress

# Remove tc qdiscs
sudo tc qdisc del dev eth0 clsact

# Verify cleanup
sudo tc filter show dev eth0 ingress
sudo tc filter show dev eth0 egress
```

## Troubleshooting

### Error: "Interface not found"

```bash
# Check interface name
ip addr show

# Update configuration with correct name
```

### Error: "Permission denied"

```bash
# Run with sudo
sudo sqproxy run

# OR grant capabilities (see above)
```

### Error: "BCC not found"

```bash
# Install BCC
sudo apt-get install python3-bpfcc

# Verify
python3 -c "import bcc; print('OK')"
```

### Error: "Failed to compile BPF program"

```bash
# Install kernel headers
sudo apt-get install linux-headers-$(uname -r)

# Check kernel version
uname -r  # Should be 4.4+
```

### Error: "tc command not found"

```bash
# Install iproute2
sudo apt-get install iproute2
```

### Packets Not Being Redirected

```bash
# 1. Verify tc filters are attached
sudo tc filter show dev eth0 ingress
sudo tc filter show dev eth0 egress

# 2. Check BPF maps have entries
sudo bpftool map dump name port_map

# 3. Verify firewall isn't blocking
sudo ufw status
sudo iptables -L -n

# 4. Test with tcpdump
sudo tcpdump -i eth0 'udp port 27015 or udp port 27016' -n
```

## Performance Tuning

### Increase Map Size

For many servers, increase BPF map capacity (requires code modification):

```python
# In source_query_proxy/ebpf/operations.py
BPF_HASH(port_map, u16, u16, 4096)  # Increase from 1024
```

### Optimize Cache Lifetimes

```yaml
defaults:
  # Reduce query frequency
  a2s_info_cache_lifetime: 10
  a2s_players_cache_lifetime: 5
  a2s_rules_cache_lifetime: 30
```

### Monitor Resource Usage

```bash
# CPU usage
top -p $(pgrep sqproxy)

# Memory usage
ps aux | grep sqproxy

# Network throughput
iftop -i eth0
```

## Next Steps

- **[eBPF Architecture](architecture.md)** - Understand internal implementation
- **[Performance Guide](performance.md)** - Benchmarks and optimization
- **[Troubleshooting](../troubleshooting.md)** - Common issues and solutions

## Additional Resources

- [BCC Installation](https://github.com/iovisor/bcc/blob/master/INSTALL.md)
- [Linux Traffic Control HOWTO](https://tldp.org/HOWTO/Traffic-Control-HOWTO/)
- [eBPF Documentation](https://ebpf.io/what-is-ebpf/)
