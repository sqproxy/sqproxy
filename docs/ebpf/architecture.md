# eBPF Architecture

Deep dive into sqproxy's internal eBPF implementation.

## System Architecture

```
┌──────────────────────────────────────────────────────┐
│              Source Query Proxy v3.0                 │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │ Template Engine (source_query_proxy/ebpf/) │    │
│  ├────────────────────────────────────────────┤    │
│  │ • BPFProgram - Program orchestrator        │    │
│  │ • BPFElement - Base class for components   │    │
│  │ • BPFStruct - C struct definitions         │    │
│  │ • BPFMap - Hash map declarations           │    │
│  │ • BPFFunction - Function definitions       │    │
│  │ • PacketRedirectOperation - Logic builder  │    │
│  └──────────────┬─────────────────────────────┘    │
│                 │                                    │
│                 ▼ Generates BPF C Code              │
│  ┌────────────────────────────────────────────┐    │
│  │ EBPFRedirector (epbf.py)                   │    │
│  ├────────────────────────────────────────────┤    │
│  │ • Lifecycle management (start/stop)        │    │
│  │ • BCC compilation                          │    │
│  │ • Map population                           │    │
│  │ • TC attachment                            │    │
│  └──────────────┬─────────────────────────────┘    │
│                 │                                    │
└─────────────────┼────────────────────────────────────┘
                  │
                  ▼ Compiles & Loads
┌──────────────────────────────────────────────────────┐
│                  BCC (BPF Compiler)                  │
├──────────────────────────────────────────────────────┤
│ • LLVM-based compilation                             │
│ • Kernel verifier validation                         │
│ • Function loading                                   │
└──────────────┬───────────────────────────────────────┘
               │
               ▼ Attaches to
┌──────────────────────────────────────────────────────┐
│              Linux Traffic Control (tc)              │
├──────────────────────────────────────────────────────┤
│  Ingress Filter          Egress Filter              │
│  tc_ingress()            tc_egress()                │
└──────────────────────────────────────────────────────┘
               │
               ▼ Processes Packets
┌──────────────────────────────────────────────────────┐
│                  Network Interface                   │
└──────────────────────────────────────────────────────┘
```

## Module Structure

### Template Engine Package

**Location**: `source_query_proxy/ebpf/`

```
source_query_proxy/ebpf/
├── __init__.py         # Package exports
├── elements.py         # BPF building blocks
├── operations.py       # High-level operations
├── program.py          # Program orchestrator
├── redirector.py       # Lifecycle manager
├── tc.py              # Traffic control operations
└── runtime.py         # Runtime utilities
```

### Core Components

#### 1. BPFProgram (program.py)

Orchestrates BPF program generation:

```python
class BPFProgram:
    def __init__(self, name: str):
        self.name = name
        self.includes = []
        self.structs = {}
        self.maps = {}
        self.functions = {}

    def apply_operation(self, operation: BPFOperation):
        """Apply high-level operation to program"""
        operation.apply_to_program(self)

    def render(self) -> str:
        """Generate complete BPF C code"""
        return f"""
        {self._render_includes()}
        {self._render_structs()}
        {self._render_maps()}
        {self._render_functions()}
        """
```

#### 2. PacketRedirectOperation (operations.py)

Generates packet redirection logic:

```python
class PacketRedirectOperation(BPFOperation):
    def apply_to_program(self, program: BPFProgram):
        # Add redirect key struct
        program.add_struct(redirect_key_struct)

        # Add hash maps
        program.add_map(port_map)
        program.add_map(addr_map)

        # Add ingress function
        program.add_function(tc_ingress_function)

        # Add egress function
        program.add_function(tc_egress_function)
```

#### 3. EBPFRedirector (redirector.py)

Manages eBPF lifecycle:

```python
class EBPFRedirector:
    async def start(self):
        """Start eBPF redirection"""
        # Generate BPF code
        bpf_code = self._generate_program()

        # Compile with BCC
        self.bpf = BPF(text=bpf_code)

        # Load functions
        self.fn_ingress = self.bpf.load_func("tc_ingress", BPF.SCHED_CLS)
        self.fn_egress = self.bpf.load_func("tc_egress", BPF.SCHED_CLS)

        # Populate maps
        self._populate_maps()

        # Attach to tc
        self._attach_tc()

    async def stop(self):
        """Stop and cleanup"""
        await self._cleanup()
```

## Generated BPF Code

### Complete Example

```c
// Auto-generated by sqproxy Template Engine

#include <uapi/linux/bpf.h>
#include <uapi/linux/if_ether.h>
#include <uapi/linux/ip.h>
#include <uapi/linux/udp.h>
#include <uapi/linux/pkt_cls.h>

// Redirect key structure
struct redirect_key_t {
    u32 ip;
    u16 port;
} __attribute__((packed));

// BPF hash maps
BPF_HASH(port_map, u16, u16, 1024);
BPF_HASH(addr_map, struct redirect_key_t, u16, 1024);

// Ingress function - handle incoming packets
int tc_ingress(struct __sk_buff *skb) {
    void *data_end = (void *)(long)skb->data_end;
    void *data = (void *)(long)skb->data;

    // Parse Ethernet header
    struct ethhdr *eth = data;
    if ((void *)(eth + 1) > data_end)
        return TC_ACT_OK;

    if (eth->h_proto != htons(ETH_P_IP))
        return TC_ACT_OK;

    // Parse IP header
    struct iphdr *ip = (void *)(eth + 1);
    if ((void *)(ip + 1) > data_end)
        return TC_ACT_OK;

    if (ip->protocol != IPPROTO_UDP)
        return TC_ACT_OK;

    // Parse UDP header
    struct udphdr *udp = (void *)(ip + 1);
    if ((void *)(udp + 1) > data_end)
        return TC_ACT_OK;

    // Validate Steam A2S protocol
    u32 *header = (u32 *)((void *)(udp + 1));
    if ((void *)(header + 1) > data_end)
        return TC_ACT_OK;

    if (*header != 0xFFFFFFFF)
        return TC_ACT_OK;

    // Check packet type
    u8 *packet_type = (u8 *)(header + 1);
    if ((void *)(packet_type + 1) > data_end)
        return TC_ACT_OK;

    // A2S_INFO=0x54, A2S_PLAYER=0x55, A2S_RULES=0x56, A2A_PING=0x69
    if (*packet_type != 0x54 && *packet_type != 0x55 &&
        *packet_type != 0x56 && *packet_type != 0x69)
        return TC_ACT_OK;

    // Lookup port mapping
    u16 orig_port = htons(udp->dest);
    u16 *new_port = port_map.lookup(&orig_port);

    if (!new_port)
        return TC_ACT_OK;

    // Redirect packet
    u16 old_port = udp->dest;
    udp->dest = htons(*new_port);

    // Recalculate UDP checksum
    bpf_l4_csum_replace(skb,
        sizeof(*eth) + sizeof(*ip) + offsetof(struct udphdr, check),
        old_port, udp->dest, sizeof(u16));

    return TC_ACT_OK;
}

// Egress function - handle outgoing packets
int tc_egress(struct __sk_buff *skb) {
    // Similar logic for reverse redirection
    // ...
    return TC_ACT_OK;
}
```

## Traffic Control Integration

### tc Qdisc Attachment

```python
def attach_tc_bpf(interface: str, bpf: BPF, ipr):
    """Attach BPF programs to tc"""

    # Get interface index
    idx = ipr.link_lookup(ifname=interface)[0]

    # Add clsact qdisc (if not exists)
    try:
        ipr.tc("add", "clsact", idx)
    except NetlinkError as e:
        if e.code != errno.EEXIST:
            raise

    # Attach ingress filter
    ipr.tc("add-filter", "bpf", idx, ":1",
           parent="ffff:fff2",  # ingress
           fd=fn_ingress.fd,
           name=fn_ingress.name,
           prio=49152,
           direct_action=True)

    # Attach egress filter
    ipr.tc("add-filter", "bpf", idx, ":2",
           parent="ffff:fff3",  # egress
           fd=fn_egress.fd,
           name=fn_egress.name,
           prio=49152,
           direct_action=True)
```

### Cleanup on Shutdown

```python
def cleanup_tc_bpf(interface: str, ipr):
    """Remove BPF programs from tc"""

    idx = ipr.link_lookup(ifname=interface)[0]

    # Remove filters
    try:
        ipr.tc("del", "clsact", idx)
    except NetlinkError:
        pass  # Already removed
```

## BPF Map Management

### Map Population

```python
def _populate_maps(self):
    """Populate BPF maps with port mappings"""

    port_map = self.bpf["port_map"]

    for server in self.servers:
        # Add port mapping
        server_port = ctypes.c_uint16(server['server_port'])
        bind_port = ctypes.c_uint16(server['bind_port'])

        port_map[server_port] = bind_port

    logger.info(f"Populated {len(port_map)} port mappings")
```

### Runtime Updates

```python
async def reload_config(self):
    """Reload configuration without restart"""

    # Load new configuration
    new_servers = load_config()

    # Update maps
    port_map = self.bpf["port_map"]
    port_map.clear()

    for server in new_servers:
        server_port = ctypes.c_uint16(server['server_port'])
        bind_port = ctypes.c_uint16(server['bind_port'])
        port_map[server_port] = bind_port

    logger.info("Configuration reloaded")
```

## Performance Optimizations

### 1. Single BPF Program

Instead of per-server programs:

```python
# ❌ Inefficient: Multiple programs
for server in servers:
    program = generate_bpf_program(server)
    load_program(program)

# ✅ Efficient: Single program + runtime maps
program = generate_single_bpf_program()
load_program(program)
populate_maps(servers)
```

### 2. Direct Action

Use `direct_action=True` to avoid extra qdisc traversal:

```python
ipr.tc("add-filter", "bpf", idx, ":1",
       direct_action=True)  # Faster
```

### 3. Early Packet Rejection

Validate packets early to skip unnecessary processing:

```c
// Ethernet check first (cheapest)
if (eth->h_proto != htons(ETH_P_IP))
    return TC_ACT_OK;  // Fast path

// Then IP
if (ip->protocol != IPPROTO_UDP)
    return TC_ACT_OK;  // Fast path

// Then UDP
// Then Steam protocol validation
```

## Error Handling

### Compilation Errors

```python
try:
    bpf = BPF(text=bpf_code)
except Exception as e:
    logger.error(f"Failed to compile BPF program: {e}")
    logger.debug(f"BPF C code:\n{bpf_code}")
    raise RuntimeError("BPF compilation failed") from e
```

### tc Attachment Errors

```python
try:
    attach_tc_bpf(interface, bpf, ipr)
except NetlinkError as e:
    logger.error(f"Failed to attach BPF to tc: {e}")
    cleanup_tc_bpf(interface, ipr)
    raise
```

### Cleanup on Failure

```python
async def stop(self):
    """Always cleanup, even on partial initialization"""

    if not self._running:
        logger.debug("Not running, but cleaning up anyway")

    try:
        cleanup_tc_bpf(self.interface, self.ipr)
    except Exception as e:
        logger.warning(f"Cleanup warning: {e}")
```

## Testing

### Unit Tests

Test template generation:

```python
def test_packet_redirect_operation():
    program = BPFProgram("test")
    operation = PacketRedirectOperation(
        server_port=27015,
        bind_port=27016
    )
    operation.apply_to_program(program)

    code = program.render()

    assert "BPF_HASH(port_map" in code
    assert "tc_ingress" in code
    assert "0xFFFFFFFF" in code  # Steam header
```

### Integration Tests

Test BCC compilation:

```python
def test_bpf_compilation():
    program = generate_program()
    code = program.render()

    # Should compile without errors
    bpf = BPF(text=code)
    assert bpf is not None

    # Functions should load
    fn_ingress = bpf.load_func("tc_ingress", BPF.SCHED_CLS)
    assert fn_ingress is not None
```

## Next Steps

- **[Performance Guide](performance.md)** - Benchmarks and tuning
- **[Setup Guide](setup.md)** - Configure eBPF
- **[eBPF Overview](overview.md)** - High-level concepts
