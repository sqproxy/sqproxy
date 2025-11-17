# eBPF Overview

Understanding how Source Query Proxy uses eBPF for high-performance packet redirection.

## What is eBPF?

**eBPF (Extended Berkeley Packet Filter)** is a revolutionary technology that allows running sandboxed programs in the Linux kernel without changing kernel source code or loading kernel modules.

### Key Features

- **Kernel-Level Execution**: Code runs in the Linux kernel for maximum performance
- **Safety**: Verifier ensures programs won't crash the kernel
- **No Kernel Modules**: No need to compile or load kernel modules
- **Dynamic**: Attach/detach programs at runtime
- **Efficient**: Minimal overhead compared to user-space processing

## Why eBPF for sqproxy?

### The Traditional Approach (User-Space)

```
Client → [Kernel] → [User-Space sqproxy] → [Kernel] → Game Server
                     ↑                       ↑
                     Slow context switches
```

**Problems**:
- Context switches between kernel and user space
- Packet copying overhead
- Higher latency
- More CPU usage

### The eBPF Approach (Kernel-Space)

```
Client → [Kernel + eBPF] → Game Server
              ↓
         [sqproxy]
         (only for query handling)
```

**Benefits**:
- ✅ Packets redirected at kernel level
- ✅ No user-space context switches
- ✅ Lower latency
- ✅ Minimal CPU overhead
- ✅ Game traffic bypasses sqproxy entirely

## How sqproxy Uses eBPF

### Architecture

```
┌────────────────────────────────────────────────────────┐
│                   Network Interface (eth0)              │
└───────────────┬────────────────────────────────────────┘
                │
        ┌───────▼────────┐
        │ eBPF Programs  │
        ├────────────────┤
        │ 1. Ingress:    │  ◄─── Incoming packets
        │    Parse UDP   │
        │    Check A2S   │
        │    Redirect    │
        │                │
        │ 2. Egress:     │  ◄─── Outgoing packets
        │    Reverse     │
        │    Redirect    │
        └───┬────────┬───┘
            │        │
     A2S    │        │    Game
    Queries │        │   Traffic
            │        │
      ┌─────▼──┐  ┌──▼──────┐
      │sqproxy │  │  Game   │
      │ :27016 │  │  Server │
      └────────┘  │ :27015  │
                  └─────────┘
```

### Packet Flow

#### 1. Incoming A2S Query

```
1. Client sends A2S_INFO to server_ip:27015
2. Packet arrives at network interface
3. eBPF ingress program:
   ├─ Parses Ethernet/IP/UDP headers
   ├─ Validates Steam protocol (0xFFFFFFFF header)
   ├─ Checks if it's an A2S packet
   ├─ Looks up port mapping: 27015 → 27016
   ├─ Rewrites destination port to 27016
   ├─ Recalculates UDP checksum
   └─ Passes packet to kernel
4. Packet delivered to sqproxy on port 27016
5. sqproxy handles query and responds
```

#### 2. Outgoing A2S Response

```
1. sqproxy sends response from port 27016
2. Packet arrives at eBPF egress program
3. eBPF egress program:
   ├─ Detects response packet
   ├─ Looks up reverse mapping: 27016 → 27015
   ├─ Rewrites source port to 27015
   ├─ Recalculates UDP checksum
   └─ Sends packet to network
4. Client receives response from server_ip:27015
```

#### 3. Game Traffic (Bypassed)

```
1. Client connects to server_ip:27015 (TCP)
2. eBPF program:
   ├─ Sees TCP packet (not UDP)
   ├─ OR sees UDP but not A2S protocol
   ├─ OR sees different destination port
   └─ Passes through unchanged
3. Packet goes directly to game server
4. No redirection, no sqproxy involvement
```

## eBPF Program Structure

### Generated BPF C Code

sqproxy generates optimized BPF C code using its template engine:

```c
// Packet redirection key structure
struct redirect_key_t {
    u32 ip;     // IP address (optional)
    u16 port;   // Port number
};

// BPF hash maps for port mappings
BPF_HASH(port_map, u16, u16, 1024);          // port → port
BPF_HASH(addr_map, redirect_key_t, u16, 1024); // (ip,port) → port

// Ingress function - incoming packets
int tc_ingress(struct __sk_buff *skb) {
    // Parse Ethernet header
    // Parse IP header
    // Parse UDP header

    // Validate Steam protocol
    if (header != 0xFFFFFFFF) return TC_ACT_OK;

    // Check packet type (A2S_INFO, A2S_PLAYER, etc.)
    // Lookup port mapping
    // Redirect if mapping found
    // Recalculate checksum

    return TC_ACT_OK;
}

// Egress function - outgoing packets
int tc_egress(struct __sk_buff *skb) {
    // Similar logic for reverse redirection
    return TC_ACT_OK;
}
```

See [Architecture](architecture.md) for detailed code structure.

## Steam Protocol Validation

eBPF program validates Steam A2S protocol for security:

### A2S Packet Structure

```
┌──────────────┬──────────┬─────────────┐
│ Header       │ Type     │ Payload     │
├──────────────┼──────────┼─────────────┤
│ 0xFFFFFFFF   │ 0x54     │ ...         │
│ (4 bytes)    │ (1 byte) │ (variable)  │
└──────────────┴──────────┴─────────────┘
```

### Supported Packet Types

| Type | Value | Name | Description |
|------|-------|------|-------------|
| A2S_INFO | 0x54 ('T') | Server info | Map, players, name, etc. |
| A2S_PLAYER | 0x55 ('U') | Player list | Player names and scores |
| A2S_RULES | 0x56 ('V') | Server rules | Cvars and rules |
| A2A_PING | 0x69 ('i') | Ping | Server ping check |

### DDoS Protection

eBPF validation provides kernel-level DDoS protection:

- ✅ Invalid packets dropped at kernel level
- ✅ No user-space processing for malicious traffic
- ✅ Minimal CPU impact from attacks
- ✅ Only valid A2S packets reach sqproxy

## Traffic Control (tc)

sqproxy uses Linux Traffic Control to attach eBPF programs.

### tc Attachment Points

```
Network Interface (eth0)
   │
   ├─ Ingress qdisc  ◄─── eBPF ingress program
   │                      (incoming packets)
   │
   └─ Egress qdisc   ◄─── eBPF egress program
                          (outgoing packets)
```

### tc Commands

View attached BPF programs:

```bash
# Show ingress filters
sudo tc filter show dev eth0 ingress

# Show egress filters
sudo tc filter show dev eth0 egress

# Output:
# filter protocol ip pref 49152 bpf chain 0
# filter protocol ip pref 49152 bpf chain 0 handle 0x1 bpf_ingress.o:[tc_ingress]
```

## BCC (BPF Compiler Collection)

sqproxy uses BCC to compile and load BPF programs.

### What is BCC?

**BCC** provides:

- Python/C API for BPF programs
- LLVM-based BPF compiler
- Helper functions for kernel interaction
- Runtime program loading

### sqproxy + BCC

```python
from bcc import BPF

# Generate BPF C code using template engine
bpf_code = program.render()

# Compile with BCC
b = BPF(text=bpf_code)

# Get function references
fn_ingress = b.load_func("tc_ingress", BPF.SCHED_CLS)
fn_egress = b.load_func("tc_egress", BPF.SCHED_CLS)

# Attach to tc
# (handled by sqproxy internally)
```

## Performance Characteristics

### Overhead

- **Packet Processing**: ~100-500 nanoseconds per packet
- **CPU Usage**: < 1% for typical query load
- **Memory**: ~1-2 MB for BPF program and maps
- **Latency**: < 1 microsecond added latency

### Scalability

- **Queries per Second**: > 100,000 qps per core
- **Concurrent Servers**: 1000+ servers in single program
- **Port Mappings**: 1024 mappings per map (configurable)

See [Performance](performance.md) for detailed benchmarks.

## Security Considerations

### eBPF Verifier

The kernel verifier ensures:

- ✅ No infinite loops
- ✅ Bounded memory access
- ✅ No kernel crashes
- ✅ Safe operations only

### Kernel Privileges

eBPF requires elevated privileges:

```bash
# Option 1: Run as root
sudo sqproxy run

# Option 2: CAP_BPF capability (kernel 5.8+)
sudo setcap cap_bpf,cap_net_admin=ep /usr/bin/python3

# Option 3: CAP_SYS_ADMIN (older kernels)
sudo setcap cap_sys_admin,cap_net_admin=ep /usr/bin/python3
```

### Attack Surface

eBPF reduces attack surface:

- ✅ Only valid A2S packets reach user space
- ✅ Invalid packets dropped at kernel level
- ✅ No processing overhead for attacks
- ✅ Sandboxed execution (verifier guarantees)

## Limitations

### What eBPF Cannot Do

- ❌ **Modify packet payload**: Only headers (IP, UDP) modified
- ❌ **Access file system**: Kernel-space only, no file I/O
- ❌ **Make network requests**: No outgoing connections
- ❌ **Complex logic**: Limited to simple conditionals and lookups

### Kernel Requirements

- **Minimum kernel**: 4.4+ (basic eBPF)
- **Recommended**: 5.8+ (CAP_BPF capability)
- **Architecture**: x86_64, ARM64 (others may work)

### System Limitations

- **tc attachment**: Requires NET_ADMIN capability
- **BCC dependency**: Needs LLVM and kernel headers
- **Single interface**: One network interface per attachment

## Comparison to sqredirect (v2.x)

| Feature | v2.x (sqredirect) | v3.0 (Built-in eBPF) |
|---------|------------------|----------------------|
| **Implementation** | External C binary | Internal Python + BCC |
| **Dependencies** | sqredirect binary | python3-bpfcc |
| **Code Generation** | Static C | Dynamic template engine |
| **Reconfiguration** | Restart required | Hot reload supported |
| **Error Handling** | Subprocess errors | Native exceptions |
| **Debugging** | Limited | Comprehensive logging |
| **Maintenance** | External dependency | Built-in |

See [Migration Guide](../migration.md) for upgrading.

## Next Steps

- **[Setup Guide](setup.md)** - Configure eBPF for your server
- **[Architecture](architecture.md)** - Deep dive into implementation
- **[Performance](performance.md)** - Benchmarks and tuning
- **[Troubleshooting](../troubleshooting.md)** - Solve eBPF issues

## Resources

- [eBPF Documentation](https://ebpf.io/)
- [BCC GitHub](https://github.com/iovisor/bcc)
- [Linux Traffic Control](https://tldp.org/HOWTO/Traffic-Control-HOWTO/)
- [Steam Server Queries](https://developer.valvesoftware.com/wiki/Server_queries)
