# Troubleshooting Guide

Common issues and solutions for Source Query Proxy.

## Installation Issues

### "BCC not found" or "No module named 'bcc'"

**Problem**: BCC Python bindings not installed.

**Solution**:
```bash
# Ubuntu/Debian
sudo apt-get install python3-bpfcc

# CentOS/RHEL
sudo yum install python3-bcc

# Verify
python3 -c "import bcc; print('OK')"
```

### "kernel headers not found"

**Problem**: Missing kernel headers for BCC compilation.

**Solution**:
```bash
# Install headers for current kernel
sudo apt-get install linux-headers-$(uname -r)

# Verify
ls /usr/src/linux-headers-$(uname -r)
```

### "pip install source-query-proxy" fails

**Problem**: Missing dependencies or Python version mismatch.

**Solution**:
```bash
# Check Python version (need 3.7+)
python3 --version

# Update pip
pip install --upgrade pip

# Install with verbose output
pip install -v source-query-proxy==3.0.0

# If still failing, install from source
git clone https://github.com/sqproxy/sqproxy.git
cd sqproxy
pip install -e .
```

## eBPF Issues

### "Permission denied" when starting

**Problem**: eBPF requires elevated privileges.

**Solutions**:

```bash
# Option 1: Run as root
sudo sqproxy run

# Option 2: Grant capabilities (kernel 5.8+)
sudo setcap cap_bpf,cap_net_admin=ep $(which python3)
sqproxy run

# Option 3: Grant capabilities (older kernels)
sudo setcap cap_sys_admin,cap_net_admin=ep $(which python3)
sqproxy run
```

### "Interface not found"

**Problem**: Configured interface doesn't exist.

**Diagnosis**:
```bash
# List interfaces
ip addr show

# Common names: eth0, ens3, enp0s3, wlan0
```

**Solution**:
Update config with correct interface name:
```yaml
ebpf:
  interface: ens3  # Use actual interface name
```

### "Failed to compile BPF program"

**Problem**: BCC compilation error.

**Diagnosis**:
```bash
# Enable debug logging
export SQPROXY_LOGLEVEL=DEBUG
sudo -E sqproxy run

# Check kernel version
uname -r  # Should be 4.4+

# Verify BCC works
python3 << 'EOF'
from bcc import BPF
BPF(text='int hello(void *ctx) { return 0; }')
print("BCC OK")
EOF
```

**Solutions**:
1. Install/update kernel headers: `sudo apt-get install linux-headers-$(uname -r)`
2. Update BCC: `sudo apt-get upgrade python3-bpfcc`
3. Check kernel version: `uname -r` (need 4.4+)

### "tc filter attach failed"

**Problem**: Cannot attach BPF to traffic control.

**Diagnosis**:
```bash
# Check tc availability
which tc

# Check existing filters
sudo tc filter show dev eth0 ingress
sudo tc filter show dev eth0 egress

# Check for conflicts
sudo tc qdisc show dev eth0
```

**Solutions**:
```bash
# Remove existing filters
sudo tc filter del dev eth0 ingress
sudo tc filter del dev eth0 egress
sudo tc qdisc del dev eth0 clsact

# Restart sqproxy
sudo systemctl restart sqproxy
```

### Packets not being redirected

**Problem**: A2S queries still reaching game server.

**Diagnosis**:
```bash
# 1. Verify eBPF is attached
sudo tc filter show dev eth0 ingress
# Should show: filter protocol ip pref 49152 bpf

# 2. Check BPF maps have entries
sudo bpftool map dump name port_map
# Should show port mappings

# 3. Capture traffic
# On game server port (should NOT see A2S queries)
sudo tcpdump -i eth0 'udp port 27015' -n -X

# On sqproxy port (should see A2S queries)
sudo tcpdump -i eth0 'udp port 27016' -n -X
```

**Solutions**:

1. **Verify configuration**:
```yaml
ebpf:
  enabled: true  # Must be true
  interface: eth0  # Correct interface
```

2. **Check firewall**:
```bash
# Disable firewall temporarily
sudo ufw disable

# Or add rules
sudo ufw allow 27016/udp
```

3. **Restart with clean slate**:
```bash
sudo systemctl stop sqproxy
sudo tc qdisc del dev eth0 clsact
sudo systemctl start sqproxy
```

## Configuration Issues

### "No servers defined"

**Problem**: Empty servers section or no config files.

**Solution**:
```yaml
# /etc/sqproxy/conf.d/10-servers.yaml
servers:
  my-server:
    network:
      server_ip: "192.168.1.100"
      server_port: 27015
      bind_port: 27016
```

### "server_port required"

**Problem**: Missing required network configuration.

**Solution**:
```yaml
servers:
  my-server:
    network:
      server_ip: "192.168.1.100"
      server_port: 27015  # Required
      bind_port: 27016     # Required
```

### Configuration not loading

**Problem**: Config files in wrong location or wrong format.

**Diagnosis**:
```bash
# Check config directories exist
ls -la /etc/sqproxy/conf.d/
ls -la ./conf.d/

# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('/etc/sqproxy/conf.d/00-globals.yaml'))"

# Test config
sqproxy config validate
sqproxy config show
```

**Solutions**:
1. Place configs in `/etc/sqproxy/conf.d/` or `./conf.d/`
2. Use `.yaml` or `.yml` extension
3. Check YAML syntax (indentation matters!)
4. Start filenames with numbers for ordering: `00-globals.yaml`, `10-servers.yaml`

## Runtime Issues

### sqproxy crashes on startup

**Diagnosis**:
```bash
# Check logs
sudo journalctl -u sqproxy -n 100 --no-pager

# Run in foreground with debug
export SQPROXY_LOGLEVEL=DEBUG
sudo -E sqproxy run

# Check for Python errors
python3 -m sqproxy.main run
```

**Common causes**:
1. Missing dependencies
2. Invalid configuration
3. Port already in use
4. Insufficient permissions

### "Address already in use"

**Problem**: Port already bound by another process.

**Diagnosis**:
```bash
# Find what's using the port
sudo lsof -i :27016
sudo netstat -tulpn | grep 27016
```

**Solutions**:
```bash
# Kill conflicting process
sudo kill <PID>

# Or use different port
# Update bind_port in config
```

### Game server shows as offline

**Problem**: sqproxy can't reach game server.

**Diagnosis**:
```bash
# Test connectivity
ping 192.168.1.100

# Test game server port
nc -u -v 192.168.1.100 27015

# Check sqproxy logs
sudo journalctl -u sqproxy | grep -i "fail\|error\|timeout"
```

**Solutions**:
```yaml
# Increase timeouts
defaults:
  a2s_response_timeout: 5
  max_a2s_fails_before_offline: 20
```

### High CPU usage

**Problem**: sqproxy consuming excessive CPU.

**Diagnosis**:
```bash
# Check CPU usage
top -p $(pgrep sqproxy)

# Profile Python
py-spy top --pid $(pgrep sqproxy)

# Check query rate
sudo tcpdump -i eth0 'udp port 27016' -n | pv -l -r
```

**Solutions**:
```yaml
# Increase cache lifetimes
defaults:
  a2s_info_cache_lifetime: 30
  a2s_players_cache_lifetime: 10
  a2s_rules_cache_lifetime: 60
```

### Memory leak

**Problem**: Memory usage grows over time.

**Diagnosis**:
```bash
# Monitor memory
watch -n 5 'ps aux | grep sqproxy'

# Profile memory
python3 -m memory_profiler sqproxy

# Check for zombie processes
ps aux | grep defunct
```

**Solutions**:
1. Restart sqproxy periodically
2. Report issue with logs
3. Update to latest version

## Network Issues

### Queries timeout

**Problem**: Clients don't receive responses.

**Diagnosis**:
```bash
# Test from client
valve-server-query 192.168.1.100:27015 info --timeout 5

# Capture packets
sudo tcpdump -i eth0 'udp port 27015 or udp port 27016' -n -vv

# Check routing
traceroute 192.168.1.100
```

**Solutions**:
1. Check firewall rules
2. Verify network connectivity
3. Increase timeouts in config
4. Check eBPF is working

### Wrong source port in responses

**Problem**: Clients see responses from wrong port.

**Diagnosis**:
```bash
# Capture outgoing packets
sudo tcpdump -i eth0 'src port 27016' -n

# Should see port rewritten to 27015
```

**Solution**:
Verify eBPF egress is working:
```bash
sudo tc filter show dev eth0 egress
# Should show BPF filter
```

### Firewall blocking traffic

**Problem**: Firewall drops eBPF-redirected packets.

**Diagnosis**:
```bash
# Check firewall
sudo iptables -L -n -v
sudo ufw status verbose

# Test with firewall disabled
sudo ufw disable
```

**Solutions**:
```bash
# Allow sqproxy port
sudo ufw allow 27016/udp

# Allow game server port
sudo ufw allow 27015/udp
sudo ufw allow 27015/tcp

# Re-enable firewall
sudo ufw enable
```

## Docker Issues

### "Operation not permitted" in container

**Problem**: Container doesn't have BPF capabilities.

**Solution**:
```yaml
# docker-compose.yml
services:
  sqproxy:
    image: sqproxy:latest
    cap_add:
      - SYS_ADMIN
      - NET_ADMIN
    # Or use privileged mode
    privileged: true
```

### Can't access host network interface

**Problem**: Container can't see host interfaces.

**Solution**:
```yaml
# Use host network mode
services:
  sqproxy:
    network_mode: host
```

## Debugging Tools

### Enable Debug Logging

```bash
export SQPROXY_LOGLEVEL=DEBUG
sudo -E sqproxy run
```

### Capture All Traffic

```bash
# Capture everything on interface
sudo tcpdump -i eth0 -w /tmp/capture.pcap

# Analyze with Wireshark
wireshark /tmp/capture.pcap
```

### Monitor BPF Activity

```bash
# Watch BPF programs
watch -n 1 'sudo bpftool prog list'

# Watch BPF maps
watch -n 1 'sudo bpftool map dump name port_map'

# tc statistics
watch -n 1 'sudo tc -s filter show dev eth0 ingress'
```

### Test Without eBPF

```yaml
ebpf:
  enabled: false
```

Run sqproxy and test if queries work (without redirection).

## Getting Help

### Collect Diagnostic Information

```bash
# System info
uname -a
cat /etc/os-release

# Kernel version
uname -r

# Python version
python3 --version

# sqproxy version
sqproxy --version

# BCC version
python3 -c "import bcc; print(bcc.__version__)"

# Configuration
sqproxy config show

# Recent logs
sudo journalctl -u sqproxy -n 100 --no-pager

# Network interfaces
ip addr show

# eBPF status
sudo tc filter show dev eth0 ingress
sudo tc filter show dev eth0 egress
sudo bpftool prog list
sudo bpftool map list
```

### Report Issue

1. Collect diagnostic info (above)
2. Create issue: https://github.com/sqproxy/sqproxy/issues
3. Include:
   - Error message
   - Configuration (remove sensitive info)
   - Logs
   - Steps to reproduce

## Common Error Messages

### "BPF program rejected by verifier"

**Cause**: Kernel verifier detected unsafe operation.

**Solution**: Report bug with BPF code and kernel version.

### "RTNETLINK answers: File exists"

**Cause**: tc filter already attached.

**Solution**:
```bash
sudo tc qdisc del dev eth0 clsact
sudo systemctl restart sqproxy
```

### "No such file or directory: /etc/sqproxy/conf.d"

**Cause**: Config directory doesn't exist.

**Solution**:
```bash
sudo mkdir -p /etc/sqproxy/conf.d
```

### "YAML syntax error"

**Cause**: Invalid YAML formatting.

**Solution**:
```bash
# Validate YAML
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Common issues:
# - Incorrect indentation (use spaces, not tabs)
# - Missing colons
# - Unquoted special characters
```

## Next Steps

- [eBPF Setup Guide](ebpf/setup.md) - Configure eBPF
- [Configuration Guide](configuration.md) - All config options
- [GitHub Issues](https://github.com/sqproxy/sqproxy/issues) - Report bugs
