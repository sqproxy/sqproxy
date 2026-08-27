# Quick Start Guide

Get Source Query Proxy up and running in 5 minutes!

## Step 1: Install

```bash
# Install sqproxy
pip install source-query-proxy==3.0.0

# Install BCC for eBPF
sudo apt-get update
sudo apt-get install -y python3-bpfcc linux-headers-$(uname -r)
```

## Step 2: Create Configuration

Create `/etc/sqproxy/conf.d/00-globals.yaml`:

```bash
sudo mkdir -p /etc/sqproxy/conf.d
sudo nano /etc/sqproxy/conf.d/00-globals.yaml
```

Add the following configuration:

```yaml
# Global eBPF settings
ebpf:
  enabled: true
  interface: eth0  # Your network interface

# Default settings for all servers
defaults:
  __global__:
    # Game server's actual port
    server_port: 27015

    # Port where sqproxy listens
    bind_port: 27016

    # Your server's IP
    bind_ip: "0.0.0.0"
```

!!! tip "Find Your Network Interface"
    ```bash
    ip addr show
    # or
    ifconfig
    ```

## Step 3: Configure Your Game Server

For a single CS:GO server at `192.168.1.100:27015`, create `/etc/sqproxy/conf.d/10-csgo-server.yaml`:

```yaml
servers:
  csgo-main:
    server_ip: "192.168.1.100"
    server_port: 27015
    bind_port: 27016
```

## Step 4: Run sqproxy

```bash
# Run in foreground (for testing)
sudo sqproxy run

# Expected output:
# INFO: Starting Source Query Proxy v3.0.0
# INFO: eBPF redirection enabled on interface eth0
# INFO: Loaded 1 server configuration(s)
# INFO: Starting eBPF redirection...
# INFO: BPF program compiled successfully
# INFO: Attached to tc ingress/egress on eth0
# INFO: Proxy ready and listening
```

!!! success "sqproxy is now running!"
    A2S queries will be redirected to sqproxy, freeing up your game server.

## Step 5: Test

From another machine, query your server:

```bash
# Using valve-server-query tool
valve-server-query 192.168.1.100:27016 info

# Using Steam Server Browser
# Open Steam → View → Servers → Add Server → 192.168.1.100:27016
```

## Step 6: Run as Service (Optional)

For production, run sqproxy as a systemd service.

### Create Service File

Create `/etc/systemd/system/sqproxy.service`:

```ini
[Unit]
Description=Source Query Proxy
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/sqproxy run
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

### Enable and Start

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable on boot
sudo systemctl enable sqproxy

# Start service
sudo systemctl start sqproxy

# Check status
sudo systemctl status sqproxy
```

## Common Configurations

### Multiple Game Servers

`/etc/sqproxy/conf.d/10-servers.yaml`:

```yaml
servers:
  csgo-dm:
    server_ip: "192.168.1.100"
    server_port: 27015
    bind_port: 27016

  csgo-competitive:
    server_ip: "192.168.1.101"
    server_port: 27015
    bind_port: 27017

  tf2-server:
    server_ip: "192.168.1.102"
    server_port: 27015
    bind_port: 27018
```

### With Custom Interface

```yaml
ebpf:
  enabled: true
  interface: ens3  # Custom interface name
```

### Without eBPF (Testing Only)

```yaml
ebpf:
  enabled: false  # Disable eBPF redirection
```

!!! warning "Performance Impact"
    Running without eBPF means all packets still go through the game server. Use eBPF for production.

## Verification Commands

### Check sqproxy Status

```bash
# View logs
sudo journalctl -u sqproxy -f

# Check if running
ps aux | grep sqproxy

# Test configuration
sqproxy config validate
```

### Check eBPF Status

```bash
# List BPF programs
sudo bpftool prog list

# Show traffic control filters
sudo tc filter show dev eth0 ingress
sudo tc filter show dev eth0 egress
```

### Monitor Traffic

```bash
# Watch sqproxy logs
sudo journalctl -u sqproxy -f --since "1 minute ago"

# Monitor network traffic
sudo tcpdump -i eth0 'udp port 27016' -n
```

## Troubleshooting Quick Fixes

### "Permission denied" Error

```bash
# Run with sudo
sudo sqproxy run
```

### "Interface not found" Error

```bash
# List interfaces
ip addr show

# Update config with correct interface name
```

### "BCC not found" Error

```bash
# Install BCC
sudo apt-get install python3-bpfcc
```

### eBPF Not Attaching

```bash
# Check kernel version (need 4.4+)
uname -r

# Install kernel headers
sudo apt-get install linux-headers-$(uname -r)
```

## Next Steps

- **[Configuration Guide](configuration.md)** - Learn all configuration options
- **[eBPF Overview](ebpf/overview.md)** - Understand how eBPF works
- **[Troubleshooting](troubleshooting.md)** - Solve common issues

## Example: Complete Setup for CS:GO

Here's a complete example for a CS:GO server:

### Game Server Settings
- **IP**: 192.168.1.100
- **Game Port**: 27015
- **Query Port**: 27016 (redirected to sqproxy)

### sqproxy Configuration

`/etc/sqproxy/conf.d/00-globals.yaml`:
```yaml
ebpf:
  enabled: true
  interface: eth0

defaults:
  __global__:
    bind_ip: "192.168.1.100"
```

`/etc/sqproxy/conf.d/10-csgo.yaml`:
```yaml
servers:
  csgo-competitive:
    server_ip: "192.168.1.100"
    server_port: 27015
    bind_port: 27016
```

### Run

```bash
sudo sqproxy run
```

### Firewall Rules

```bash
# Allow query traffic to sqproxy
sudo ufw allow 27016/udp

# Allow game traffic to server
sudo ufw allow 27015/udp
sudo ufw allow 27015/tcp
```

### Verify

```bash
# From remote machine
valve-server-query 192.168.1.100:27016 info

# Should show server info without hitting the game server
```

!!! success "Complete!"
    Your CS:GO server is now using sqproxy for query handling!
