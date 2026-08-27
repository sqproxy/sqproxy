# Configuration Guide

Complete reference for configuring Source Query Proxy.

## Configuration Files

sqproxy uses YAML configuration files located in:

- `/etc/sqproxy/conf.d/` - System-wide configuration
- `./conf.d/` - Local directory configuration

Files are processed in **alphabetical order**. Use prefixes to control loading order:

```
/etc/sqproxy/conf.d/
├── 00-globals.yaml      # Global defaults
├── 10-csgo-servers.yaml # CS:GO servers
├── 20-tf2-servers.yaml  # TF2 servers
└── 99-overrides.yaml    # Final overrides
```

## Configuration Structure

### Basic Structure

```yaml
# Global defaults (applied to all servers)
defaults:
  __global__: true
  network:
    server_ip: "192.168.1.100"
    # ...other defaults

# eBPF configuration
ebpf:
  enabled: true
  interface: eth0

# Server definitions
servers:
  server-name:
    network:
      server_port: 27015
      bind_port: 27016
```

## eBPF Configuration

### ebpf Section

Controls eBPF packet redirection (v3.0.0+).

```yaml
ebpf:
  # Enable/disable eBPF redirection
  enabled: true

  # Network interface for eBPF attachment
  # Use 'ip addr show' to find your interface
  interface: eth0

  # Optional: Disable redirection for specific operations
  # Useful for debugging
  no_redirect: false
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable eBPF packet redirection |
| `interface` | string | auto-detect | Network interface name (eth0, ens3, etc.) |
| `no_redirect` | boolean | `false` | Disable packet redirection (debug only) |

!!! warning "Deprecated Options (v2.x)"
    The following options are **ignored** in v3.0.0+:

    - `executable` - No longer uses external sqredirect
    - `script_path` - BPF code generated internally

    See [Migration Guide](migration.md) for details.

## Defaults Section

### Global Defaults

Use `__global__: true` to apply defaults to all subsequent configuration files:

```yaml
# 00-globals.yaml
defaults:
  __global__: true  # Apply to all servers in all files
  network:
    server_ip: "192.168.1.100"
    bind_ip: null
  a2s_info_cache_lifetime: 5
```

### Local Defaults

Use `__global__: false` (or omit) for file-specific defaults:

```yaml
# 10-csgo-servers.yaml
defaults:
  __global__: false  # Apply only to servers in this file
  network:
    server_ip: "192.168.1.101"
  a2s_info_cache_lifetime: 10
```

## Network Configuration

### network Section

Defines network endpoints for game server and proxy.

```yaml
defaults:
  network:
    # Game server settings
    server_ip: "192.168.1.100"
    server_port: 27015

    # Proxy settings
    bind_ip: null  # or "0.0.0.0" or specific IP
    bind_port: 0   # 0 = auto-assign

    # eBPF redirection control
    ebpf_no_redirect: false
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `server_ip` | string | **required** | Game server IP address |
| `server_port` | integer | **required** | Game server query port |
| `bind_ip` | string/null | `server_ip` | IP for sqproxy to listen on |
| `bind_port` | integer | `0` | Port for sqproxy to listen on (0 = auto) |
| `ebpf_no_redirect` | boolean | `false` | Disable eBPF redirection for this server |

#### Examples

**Basic Configuration**:
```yaml
network:
  server_ip: "192.168.1.100"
  server_port: 27015
  bind_port: 27016
```

**Listen on All Interfaces**:
```yaml
network:
  server_ip: "192.168.1.100"
  server_port: 27015
  bind_ip: "0.0.0.0"
  bind_port: 27016
```

**Auto-assign Port**:
```yaml
network:
  server_ip: "192.168.1.100"
  server_port: 27015
  bind_port: 0  # sqproxy will choose available port
```

## Cache Configuration

### A2S Cache Lifetimes

Control how often sqproxy queries the game server:

```yaml
defaults:
  # A2S_INFO - Server name, map, players, etc.
  a2s_info_cache_lifetime: 5

  # A2S_PLAYERS - Player list with scores
  a2s_players_cache_lifetime: 1

  # A2S_RULES - Server cvars and rules
  a2s_rules_cache_lifetime: 5

  # Response timeout
  a2s_response_timeout: 1
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `a2s_info_cache_lifetime` | integer | `5` | Seconds to cache server info |
| `a2s_players_cache_lifetime` | integer | `1` | Seconds to cache player list |
| `a2s_rules_cache_lifetime` | integer | `5` | Seconds to cache server rules |
| `a2s_response_timeout` | integer | `1` | Timeout waiting for game server |

!!! tip "DDoS Protection"
    Some games ban IPs that query too frequently. Increase cache lifetimes if you experience bans:
    ```yaml
    a2s_info_cache_lifetime: 10
    a2s_players_cache_lifetime: 5
    a2s_rules_cache_lifetime: 10
    ```

## Advanced Options

### A2S_RULES Handling

Disable A2S_RULES queries for HLDS servers or broken implementations:

```yaml
defaults:
  # Disable A2S_RULES queries
  no_a2s_rules: true
```

!!! note "CS:GO A2S_RULES Fix"
    CS:GO has broken A2S_RULES. Use [this SourceMod plugin](https://forums.alliedmods.net/showthread.php?t=236521) to fix it.

### Startup Behavior

```yaml
defaults:
  # Wait for game server responses before starting redirection
  wait_ready_graceful_period: 5
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `wait_ready_graceful_period` | integer | `5` | Seconds to wait for server responses at startup |

### Server Offline Detection

```yaml
defaults:
  # Mark server offline after N consecutive failures
  max_a2s_fails_before_offline: 10
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_a2s_fails_before_offline` | integer | `10` | Failed requests before marking server offline |

!!! warning "Offline Behavior"
    When a server is marked offline, sqproxy **stops responding to queries** for that server. This allows monitoring tools to detect the issue.

## Server Definitions

### servers Section

Define individual game servers:

```yaml
servers:
  # Server identifier (must be unique)
  csgo-competitive:
    network:
      server_ip: "192.168.1.100"
      server_port: 27015
      bind_port: 27016

  csgo-deathmatch:
    network:
      server_ip: "192.168.1.101"
      server_port: 27015
      bind_port: 27017
    # Override cache lifetime for this server
    a2s_info_cache_lifetime: 10
```

### Override Defaults

Server-specific settings override defaults:

```yaml
defaults:
  __global__: true
  network:
    server_ip: "192.168.1.100"
  a2s_info_cache_lifetime: 5

servers:
  fast-server:
    network:
      server_port: 27015
      bind_port: 27016
    # Override: cache for 1 second
    a2s_info_cache_lifetime: 1

  slow-server:
    network:
      server_port: 27016
      bind_port: 27017
    # Override: cache for 30 seconds
    a2s_info_cache_lifetime: 30
```

## Complete Examples

### Example 1: Single CS:GO Server

`/etc/sqproxy/conf.d/00-config.yaml`:

```yaml
ebpf:
  enabled: true
  interface: eth0

defaults:
  __global__: true
  network:
    server_ip: "192.168.1.100"
    bind_ip: null
  a2s_info_cache_lifetime: 5
  a2s_players_cache_lifetime: 1
  a2s_rules_cache_lifetime: 5

servers:
  csgo-main:
    network:
      server_port: 27015
      bind_port: 27016
```

### Example 2: Multiple Servers

`/etc/sqproxy/conf.d/00-globals.yaml`:

```yaml
ebpf:
  enabled: true
  interface: eth0

defaults:
  __global__: true
  network:
    server_ip: "192.168.1.100"
  a2s_info_cache_lifetime: 5
  a2s_players_cache_lifetime: 1
```

`/etc/sqproxy/conf.d/10-csgo.yaml`:

```yaml
servers:
  csgo-competitive:
    network:
      server_port: 27015
      bind_port: 27016

  csgo-casual:
    network:
      server_port: 27016
      bind_port: 27017
```

`/etc/sqproxy/conf.d/20-tf2.yaml`:

```yaml
servers:
  tf2-payload:
    network:
      server_ip: "192.168.1.101"
      server_port: 27015
      bind_port: 27018
```

### Example 3: Different IPs

```yaml
ebpf:
  enabled: true
  interface: eth0

servers:
  server-1:
    network:
      server_ip: "192.168.1.100"
      server_port: 27015
      bind_port: 27016

  server-2:
    network:
      server_ip: "192.168.1.101"
      server_port: 27015
      bind_port: 27016

  server-3:
    network:
      server_ip: "192.168.1.102"
      server_port: 27015
      bind_port: 27016
```

### Example 4: High-Traffic Server

For servers with many queries:

```yaml
servers:
  high-traffic:
    network:
      server_ip: "192.168.1.100"
      server_port: 27015
      bind_port: 27016
    # Aggressive caching
    a2s_info_cache_lifetime: 30
    a2s_players_cache_lifetime: 10
    a2s_rules_cache_lifetime: 60
    # Longer timeout
    a2s_response_timeout: 2
    # More tolerant to failures
    max_a2s_fails_before_offline: 20
```

## Configuration Validation

### Validate Configuration

```bash
# Check configuration syntax
sqproxy config validate

# Show parsed configuration
sqproxy config show

# Show configuration for specific server
sqproxy config show --server csgo-main
```

### Common Validation Errors

#### Error: "No servers defined"

```yaml
# ❌ Wrong: empty servers section
servers:

# ✅ Correct: at least one server
servers:
  my-server:
    network:
      server_port: 27015
```

#### Error: "server_port required"

```yaml
# ❌ Wrong: missing server_port
servers:
  my-server:
    network:
      bind_port: 27016

# ✅ Correct: both ports defined
servers:
  my-server:
    network:
      server_port: 27015
      bind_port: 27016
```

## Environment Variables

Override configuration with environment variables:

```bash
# Set log level
export SQPROXY_LOGLEVEL=DEBUG

# Set error log path
export SQPROXY_ERROR_LOG=/var/log/sqproxy/error.log

# Run sqproxy
sqproxy run
```

| Variable | Default | Description |
|----------|---------|-------------|
| `SQPROXY_LOGLEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `SQPROXY_ERROR_LOG` | `/dev/null` | Error log file path |

## Best Practices

### 1. Use Global Defaults

Define common settings once in `00-globals.yaml`:

```yaml
defaults:
  __global__: true
  a2s_info_cache_lifetime: 5
  a2s_players_cache_lifetime: 1
```

### 2. Organize by Game Type

```
conf.d/
├── 00-globals.yaml
├── 10-csgo-servers.yaml
├── 20-tf2-servers.yaml
└── 30-css-servers.yaml
```

### 3. Use Descriptive Server Names

```yaml
servers:
  csgo-competitive-dust2:  # ✅ Good
  csgo-dm-mirage:          # ✅ Good
  server1:                 # ❌ Bad
  srv:                     # ❌ Bad
```

### 4. Comment Your Config

```yaml
servers:
  # Main competitive server - 128 tick
  csgo-comp:
    network:
      server_port: 27015
      bind_port: 27016
    # Longer cache for stable server
    a2s_info_cache_lifetime: 10
```

### 5. Version Control

Keep configs in git:

```bash
cd /etc/sqproxy
git init
git add conf.d/
git commit -m "Initial sqproxy configuration"
```

## Troubleshooting

See [Troubleshooting Guide](troubleshooting.md) for configuration-related issues.

## Next Steps

- **[eBPF Setup](ebpf/setup.md)** - Configure eBPF packet redirection
- **[Quick Start](quickstart.md)** - Get started quickly
- **[API Reference](api-reference.md)** - Python API documentation
