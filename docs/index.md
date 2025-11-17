# Source Query Proxy

**High-performance proxy for Source Engine game servers with built-in eBPF packet redirection**

[![Version](https://img.shields.io/badge/version-3.0.0-blue.svg)](https://github.com/sqproxy/sqproxy/releases)
[![Python](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Overview

Source Query Proxy (sqproxy) is a specialized proxy server designed to offload A2S query handling from Source Engine game servers. By redirecting query packets at the kernel level using eBPF, sqproxy eliminates the performance overhead of query processing on game servers.

### Key Features

- **eBPF Packet Redirection**: Built-in eBPF implementation using BCC (BPF Compiler Collection)
- **Zero Configuration Changes**: Drop-in replacement for external sqredirect
- **High Performance**: Kernel-level packet redirection with minimal overhead
- **Async Architecture**: Modern Python async/await for efficient I/O
- **Dynamic Reconfiguration**: Reload eBPF config without restart
- **Template Engine**: Class-based BPF C code generation
- **Comprehensive Testing**: Unit tests, integration tests, Docker tests

## Why sqproxy?

### The Problem

Source Engine game servers (CS:GO, CS:Source, Left 4 Dead 2, etc.) run in a single thread and cannot utilize more than one CPU core for game logic. When servers receive many A2S query requests (server browser queries), they spend valuable CPU time processing and responding to these queries instead of running the game.

### Traditional Solutions Don't Work

**IPTables/NAT Limitations**: Using IPTables (NAT) to redirect queries to a proxy creates routing table entries that also redirect player connections to the proxy, breaking game connectivity.

### The sqproxy Solution

sqproxy uses **eBPF (Extended Berkeley Packet Filter)** for intelligent packet redirection:

- ✅ Redirects A2S query packets to the proxy at kernel level
- ✅ Allows game connection packets to reach the server directly
- ✅ No routing table pollution
- ✅ Minimal performance overhead
- ✅ Validates Steam protocol packets for DDoS protection

## Quick Start

### Installation

```bash
# Install sqproxy
pip install source-query-proxy==3.0.0

# Install BCC for eBPF support
sudo apt-get update
sudo apt-get install python3-bpfcc linux-headers-$(uname -r)
```

### Basic Configuration

Create `/etc/sqproxy/conf.d/00-globals.yaml`:

```yaml
ebpf:
  enabled: true

defaults:
  __global__:
    server_port: 27015
    bind_port: 27016
```

### Run

```bash
# Run with eBPF (requires root/CAP_BPF)
sudo sqproxy run
```

See [Installation Guide](installation.md) for detailed instructions.

## What's New in v3.0.0

!!! success "v3.0.0 - Internal eBPF Implementation"

    **Major Features**:

    - ✅ **Built-in eBPF**: Replaced external sqredirect with internal BCC-based implementation
    - ✅ **EBPFRedirector Class**: Async lifecycle manager with start/stop/restart methods
    - ✅ **Template Engine**: Dynamic BPF C code generation (Django-style)
    - ✅ **Better Error Handling**: Exception chaining and detailed diagnostics
    - ✅ **Zero Breaking Changes**: Drop-in replacement for v2.x

    **Migration**: See [Migration Guide](migration.md)

## Architecture

```
┌─────────────┐
│   Client    │  A2S Query Request
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│  eBPF (Kernel Space)                │
│  ┌──────────────────────────────┐  │
│  │ Packet Filter & Redirector  │  │◄── Generated from Template Engine
│  └──────────────────────────────┘  │
└─────┬───────────────────┬───────────┘
      │                   │
      │ A2S Queries       │ Game Traffic
      ▼                   ▼
┌─────────────┐     ┌─────────────┐
│   sqproxy   │     │ Game Server │
│   (Proxy)   │     │  (CS:GO)    │
└─────────────┘     └─────────────┘
```

## Documentation

- **[Installation Guide](installation.md)** - Detailed installation instructions
- **[Configuration Guide](configuration.md)** - Configuration options and examples
- **[eBPF Overview](ebpf/overview.md)** - Understanding eBPF integration
- **[Migration Guide](migration.md)** - Migrating from v2.x to v3.0
- **[API Reference](api-reference.md)** - Python API documentation
- **[Development Guide](development.md)** - Contributing to sqproxy

## Supported Games

All Source Engine games that use A2S queries:

- Counter-Strike: Global Offensive (CS:GO)
- Counter-Strike 2 (CS2)
- Counter-Strike: Source
- Team Fortress 2
- Left 4 Dead / Left 4 Dead 2
- Garry's Mod
- Half-Life 2: Deathmatch
- Day of Defeat: Source
- And more...

## Requirements

- **Python**: 3.7 or higher
- **Linux Kernel**: 4.4+ (for eBPF support)
- **BCC**: BPF Compiler Collection (python3-bpfcc)
- **Privileges**: CAP_BPF or CAP_SYS_ADMIN capability

## Community & Support

- **GitHub Issues**: [Report bugs](https://github.com/sqproxy/sqproxy/issues)
- **Documentation**: [Full documentation](https://github.com/sqproxy/sqproxy/tree/main/docs)
- **Source Code**: [GitHub Repository](https://github.com/sqproxy/sqproxy)

## License

MIT License - see [LICENSE](license.md) for details.

## Credits

Source Engine message handling inspired by [Python-valve](https://github.com/serverstf/python-valve).
