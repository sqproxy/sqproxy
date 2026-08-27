# eBPF Template Engine - Architecture Design

## Overview

Replace external `sqredirect` dependency with internal class-based eBPF code generation system. This is a refactoring - no new eBPF features, just porting existing redirect.c functionality.

## Design Decisions

- **Template Engine**: Class-based (similar to Django migrations operations)
- **BPF Framework**: BCC (Python), future migration to bpfman.io
- **Backward Compatibility**: None - breaking change, remove sqredirect
- **Scope**: Port redirect.c logic only, no new features
- **Testing**: Docker + docker-compose with virtual networks

## Architecture

### Class Hierarchy

```python
# Base building blocks
class BPFElement:
    """Base class for all BPF code elements"""
    def render(self) -> str:
        raise NotImplementedError

class BPFStruct(BPFElement):
    """C struct definition"""
    def __init__(self, name: str, fields: List[Tuple[str, str]]):
        self.name = name
        self.fields = fields  # [(type, name), ...]

    def render(self) -> str:
        # Generate: struct addr_key_t { u32 ip; u16 port; };

class BPFMap(BPFElement):
    """BPF hash map (BPF_HASH, BPF_ARRAY, etc.)"""
    def __init__(self, name: str, key_type: str, value_type: str,
                 max_entries: int = 10240):
        self.name = name
        self.key_type = key_type
        self.value_type = value_type
        self.max_entries = max_entries

    def render(self) -> str:
        # Generate: BPF_HASH(port_map, u16, u16, 1024);

class BPFFunction(BPFElement):
    """BPF program function"""
    def __init__(self, name: str, return_type: str = "int",
                 params: List[Tuple[str, str]] = None):
        self.name = name
        self.return_type = return_type
        self.params = params or [("struct __sk_buff", "*skb")]
        self.body_parts = []  # List of code blocks

    def add_code(self, code: str):
        """Add code block to function body"""
        self.body_parts.append(code)

    def render(self) -> str:
        # Generate full function with signature + body

# High-level operations (composable)
class BPFOperation:
    """Base class for composable BPF operations (like Django Operation)"""
    def apply(self, program: 'BPFProgram'):
        raise NotImplementedError

class PacketRedirectOperation(BPFOperation):
    """Redirect packets from server_port to bind_port"""
    def __init__(self, server_port: int, bind_port: int,
                 bind_ip: str = None, use_ipport_key: bool = False):
        self.server_port = server_port
        self.bind_port = bind_port
        self.bind_ip = bind_ip
        self.use_ipport_key = use_ipport_key

    def apply(self, program: 'BPFProgram'):
        # Add required maps
        if self.use_ipport_key:
            program.add_struct(BPFStruct("addr_key_t", [
                ("u32", "ip"),
                ("u16", "port")
            ]))
            program.add_map(BPFMap("addr_map", "struct addr_key_t", "u16"))
        else:
            program.add_map(BPFMap("port_map", "u16", "u16"))

        # Add incoming/outgoing functions
        program.add_function(self._create_incoming_function())
        program.add_function(self._create_outgoing_function())

    def _create_incoming_function(self) -> BPFFunction:
        """Port redirect.c incoming() logic"""
        func = BPFFunction("incoming")
        func.add_code("""
    // Parse Ethernet header
    void *data_end = (void *)(long)skb->data_end;
    void *data = (void *)(long)skb->data;
    struct ethhdr *eth = data;

    if (data + sizeof(*eth) > data_end)
        return TC_ACT_OK;

    if (eth->h_proto != htons(ETH_P_IP))
        return TC_ACT_OK;
        """)
        # ... more code generation
        return func

    def _create_outgoing_function(self) -> BPFFunction:
        """Port redirect.c outgoing() logic"""
        # Similar to incoming

# Main program class
class BPFProgram:
    """Complete BPF program that can be compiled and loaded"""
    def __init__(self, name: str):
        self.name = name
        self.includes = [
            "<uapi/linux/bpf.h>",
            "<uapi/linux/if_ether.h>",
            "<uapi/linux/ip.h>",
            "<uapi/linux/udp.h>",
            "<uapi/linux/pkt_cls.h>"
        ]
        self.structs = []
        self.maps = []
        self.functions = []

    def add_struct(self, struct: BPFStruct):
        self.structs.append(struct)

    def add_map(self, map: BPFMap):
        self.maps.append(map)

    def add_function(self, func: BPFFunction):
        self.functions.append(func)

    def apply_operation(self, operation: BPFOperation):
        """Apply a high-level operation to this program"""
        operation.apply(self)

    def render(self) -> str:
        """Generate complete BPF C code"""
        parts = []

        # Includes
        for inc in self.includes:
            parts.append(f"#include {inc}")
        parts.append("")

        # Structs
        for struct in self.structs:
            parts.append(struct.render())
            parts.append("")

        # Maps
        for map in self.maps:
            parts.append(map.render())
            parts.append("")

        # Functions
        for func in self.functions:
            parts.append(func.render())
            parts.append("")

        return "\n".join(parts)
```

### Usage Example

```python
# In epbf.py or new ebpf_generator.py

from source_query_proxy.ebpf_template import BPFProgram, PacketRedirectOperation

def generate_redirect_program(server_port: int, bind_port: int,
                              bind_ip: str = None) -> str:
    """Generate BPF program for port redirection"""
    program = BPFProgram(f"redirect_{server_port}")

    # Apply redirect operation
    redirect_op = PacketRedirectOperation(
        server_port=server_port,
        bind_port=bind_port,
        bind_ip=bind_ip,
        use_ipport_key=bind_ip is not None
    )
    program.apply_operation(redirect_op)

    # Generate C code
    return program.render()

# Load with BCC
from bcc import BPF

bpf_code = generate_redirect_program(27015, 27016)
b = BPF(text=bpf_code)
fn_incoming = b.load_func("incoming", BPF.SCHED_CLS)
fn_outgoing = b.load_func("outgoing", BPF.SCHED_CLS)
# ... attach to tc
```

## Implementation Plan

### Phase 1: Core Template Engine
1. Create `source_query_proxy/ebpf/` package
2. Implement base classes: `BPFElement`, `BPFStruct`, `BPFMap`, `BPFFunction`
3. Implement `BPFProgram` orchestrator
4. Implement `BPFOperation` base class

### Phase 2: Port sqredirect Logic
1. Implement `PacketRedirectOperation`
2. Port `incoming()` function logic from redirect.c
3. Port `outgoing()` function logic from redirect.c
4. Handle both USE_IPPORT_KEY modes
5. Unit tests for code generation

### Phase 3: Integration
1. Update `epbf.py` to use new generator
2. Remove sqredirect subprocess calls
3. Handle BCC compilation and loading
4. Config integration (read server/bind ports from YAML)

### Phase 4: Docker Testing Infrastructure
1. Create `tests/docker/` structure:
   ```
   tests/docker/
   ├── docker-compose.yml
   ├── Dockerfile.gameserver     # Simulated game server
   ├── Dockerfile.sqproxy        # sqproxy with eBPF
   ├── Dockerfile.client         # A2S query client
   └── test_redirect.py          # Integration tests
   ```

2. docker-compose.yml with networks:
   ```yaml
   version: '3.8'
   services:
     gameserver:
       build:
         context: .
         dockerfile: Dockerfile.gameserver
       networks:
         game_net:
           ipv4_address: 10.5.0.10
       ports:
         - "27015:27015/udp"

     sqproxy:
       build:
         context: ../..
         dockerfile: tests/docker/Dockerfile.sqproxy
       privileged: true  # For eBPF
       cap_add:
         - NET_ADMIN
         - SYS_ADMIN
       networks:
         game_net:
           ipv4_address: 10.5.0.20

     client:
       build:
         context: .
         dockerfile: Dockerfile.client
       networks:
         game_net:
           ipv4_address: 10.5.0.30
       depends_on:
         - gameserver
         - sqproxy

   networks:
     game_net:
       driver: bridge
       ipam:
         config:
           - subnet: 10.5.0.0/24
   ```

3. Test scenarios:
   - Send A2S_INFO to game server port
   - Verify sqproxy intercepts and responds
   - Verify game server never sees the packet
   - Test outgoing packet rewriting
   - Test with/without bind_ip

### Phase 5: Documentation
1. Update README.md (remove sqredirect references)
2. Add architecture docs
3. Migration guide for users
4. Testing guide

## File Structure

```
source_query_proxy/
├── ebpf/
│   ├── __init__.py
│   ├── elements.py          # BPFElement, BPFStruct, BPFMap, BPFFunction
│   ├── operations.py        # BPFOperation, PacketRedirectOperation
│   └── program.py           # BPFProgram
├── epbf.py                  # Updated to use new generator
└── ebpf_template.py         # Keep for reference, mark deprecated

tests/
├── test_ebpf_generation.py  # Unit tests for template engine
└── docker/                  # Integration tests
    ├── docker-compose.yml
    ├── Dockerfile.*
    └── test_redirect.py

```

## Testing Strategy

### Unit Tests (pytest)
- Test each BPF element renders correct C code
- Test operation composition
- Test program generation
- Verify generated code is valid C (parse with pycparser?)

### Integration Tests (Docker)
- Real packet capture with tcpdump
- Verify redirect behavior
- Test with actual Source Engine queries
- Performance baseline (not 1M RPS, just no regression)

## Migration Notes

**Breaking Changes:**
- Remove sqredirect from requirements
- Remove subprocess calls in epbf.py
- Require BCC installed (already required)
- Require kernel >= 4.x with eBPF support

**Deprecation:**
- Mark `ebpf_template.py` as deprecated (keep for reference)
- Update installation docs

## Future Enhancements (NOT in this issue)
- Whitelist/blacklist (issue #130)
- Rate limiting (issue #103)
- Fast challenge response (issue #104)
- Tail call architecture from ebpf_template.py design

## Questions for Review
1. Is class-based approach clear and maintainable?
2. Should we use Jinja2 for code blocks instead of string building?
3. Docker test infrastructure - is this sufficient?
4. Should we keep ebpf_template.py or delete it?

---
**Issue**: #131
**Author**: spumer
**Status**: Design Phase
