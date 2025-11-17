# Installation Guide

This guide covers the installation of Source Query Proxy v3.0.0 with built-in eBPF support.

## Prerequisites

### System Requirements

- **Operating System**: Linux (kernel 4.4+)
- **Python**: 3.7 or higher
- **Architecture**: x86_64 (amd64) or ARM64
- **Privileges**: Root access or CAP_BPF/CAP_SYS_ADMIN capability

### Check Your System

```bash
# Check Python version
python3 --version  # Should be 3.7+

# Check kernel version
uname -r  # Should be 4.4+

# Check if running as root (for eBPF)
id -u  # Should return 0 for root
```

## Installation Methods

### Method 1: PyPI (Recommended)

Install sqproxy from Python Package Index:

```bash
pip install source-query-proxy==3.0.0
```

!!! tip "Virtual Environment"
    It's recommended to use a virtual environment:
    ```bash
    python3 -m venv sqproxy-env
    source sqproxy-env/bin/activate
    pip install source-query-proxy==3.0.0
    ```

### Method 2: From Source

Clone and install from GitHub:

```bash
# Clone repository
git clone https://github.com/sqproxy/sqproxy.git
cd sqproxy

# Install with Poetry
poetry install

# Or install with pip
pip install -e .
```

### Method 3: Using pyenv

Install any Python version without root privileges:

```bash
# Install pyenv
curl https://pyenv.run | bash

# Install Python 3.11
pyenv install 3.11.0
pyenv global 3.11.0

# Install sqproxy
pip install source-query-proxy==3.0.0
```

## eBPF Dependencies

!!! warning "Required for eBPF Functionality"
    sqproxy v3.0.0 requires BCC (BPF Compiler Collection) for eBPF packet redirection.

### Ubuntu/Debian

```bash
# Update package list
sudo apt-get update

# Install BCC and kernel headers
sudo apt-get install -y \
    python3-bpfcc \
    linux-headers-$(uname -r) \
    bpfcc-tools

# Verify installation
python3 -c "import bcc; print('BCC version:', bcc.__version__)"
```

### CentOS/RHEL 8+

```bash
# Enable PowerTools/CodeReady repository
sudo dnf config-manager --set-enabled powertools

# Install BCC
sudo dnf install -y \
    bcc-tools \
    python3-bcc \
    kernel-devel-$(uname -r)
```

### Fedora

```bash
sudo dnf install -y \
    bcc-tools \
    python3-bcc \
    kernel-devel
```

### Arch Linux

```bash
sudo pacman -S bcc bcc-tools linux-headers
```

## Verification

### Test sqproxy Installation

```bash
# Check version
sqproxy --version

# Show help
sqproxy --help

# Test configuration
sqproxy config validate
```

### Test BCC Installation

```bash
# Test BCC Python bindings
python3 << 'EOF'
from bcc import BPF

# Simple test program
program = r"""
int hello(void *ctx) {
    return 0;
}
"""

b = BPF(text=program)
print("✅ BCC is working correctly!")
EOF
```

!!! success "Expected Output"
    ```
    ✅ BCC is working correctly!
    ```

## Directory Structure

After installation, create the configuration directory:

```bash
# Create config directories
sudo mkdir -p /etc/sqproxy/conf.d

# Set appropriate permissions
sudo chown -R $USER:$USER /etc/sqproxy
```

## Next Steps

1. **[Quick Start Guide](quickstart.md)** - Get started with basic configuration
2. **[Configuration Guide](configuration.md)** - Learn about configuration options
3. **[eBPF Setup](ebpf/setup.md)** - Configure eBPF packet redirection

## Troubleshooting

### BCC Installation Issues

#### Error: "bpfcc not found"

```bash
# Ensure you have the correct package name
apt-cache search bpfcc
# or
dnf search bcc
```

#### Error: "kernel headers not found"

```bash
# Install matching kernel headers
sudo apt-get install linux-headers-$(uname -r)

# Verify installation
ls /usr/src/linux-headers-$(uname -r)
```

#### Error: "Python bcc module not found"

```bash
# Check Python path
python3 -c "import sys; print('\n'.join(sys.path))"

# Install to correct Python version
sudo apt-get install python3-bpfcc
```

### Permission Issues

#### Error: "Operation not permitted"

eBPF requires elevated privileges:

```bash
# Option 1: Run as root
sudo sqproxy run

# Option 2: Add CAP_BPF capability (kernel 5.8+)
sudo setcap cap_bpf,cap_net_admin=ep $(which python3)

# Option 3: Add CAP_SYS_ADMIN capability (older kernels)
sudo setcap cap_sys_admin,cap_net_admin=ep $(which python3)
```

### Import Errors

#### Error: "No module named 'source_query_proxy'"

```bash
# Check installation
pip list | grep source-query-proxy

# Reinstall if needed
pip uninstall source-query-proxy
pip install source-query-proxy==3.0.0
```

## Platform-Specific Notes

### Docker

When running in Docker, you need privileged mode or specific capabilities:

```bash
# Option 1: Privileged mode
docker run --privileged sqproxy

# Option 2: Specific capabilities
docker run --cap-add=SYS_ADMIN --cap-add=NET_ADMIN sqproxy
```

See [Docker Deployment](docker.md) for detailed instructions.

### WSL2 (Windows Subsystem for Linux)

eBPF support in WSL2 requires kernel 5.10.60.1+:

```bash
# Check WSL kernel version
uname -r

# Update WSL if needed
wsl --update
```

!!! warning "WSL1 Not Supported"
    WSL1 does not support eBPF. You must use WSL2.

## Upgrading

### From v2.x to v3.0.0

See the [Migration Guide](migration.md) for detailed upgrade instructions.

Quick upgrade:

```bash
# Install BCC first
sudo apt-get install python3-bpfcc linux-headers-$(uname -r)

# Upgrade sqproxy
pip install --upgrade source-query-proxy

# Restart service
sudo systemctl restart sqproxy
```

### From v3.0.0-beta to v3.0.0

```bash
pip install --upgrade source-query-proxy==3.0.0
sudo systemctl restart sqproxy
```

## Uninstallation

```bash
# Stop service if running
sudo systemctl stop sqproxy
sudo systemctl disable sqproxy

# Uninstall sqproxy
pip uninstall source-query-proxy

# Optionally remove BCC (if not used by other tools)
sudo apt-get remove python3-bpfcc bpfcc-tools

# Remove configuration
sudo rm -rf /etc/sqproxy
```

## Getting Help

- **GitHub Issues**: [Report installation problems](https://github.com/sqproxy/sqproxy/issues)
- **Troubleshooting**: [Common issues and solutions](troubleshooting.md)
- **Community**: Join discussions on GitHub
