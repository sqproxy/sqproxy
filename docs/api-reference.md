# API Reference

Python API documentation for Source Query Proxy.

## eBPF Package

### source_query_proxy.ebpf

High-level eBPF template engine and runtime.

#### BPFProgram

Main orchestrator for BPF program generation.

```python
from source_query_proxy.ebpf import BPFProgram

program = BPFProgram(name="my_program")
```

**Methods**:

##### `__init__(name: str)`

Create new BPF program.

**Parameters**:
- `name` (str): Program name

##### `add_include(path: str) -> None`

Add C include directive.

```python
program.add_include("<uapi/linux/bpf.h>")
```

##### `add_struct(struct: BPFStruct) -> None`

Add struct definition.

```python
from source_query_proxy.ebpf import BPFStruct

struct = BPFStruct("my_struct", [
    ("u32", "field1"),
    ("u16", "field2")
])
program.add_struct(struct)
```

##### `add_map(bpf_map: BPFMap) -> None`

Add BPF hash map.

```python
from source_query_proxy.ebpf import BPFMap

port_map = BPFMap("port_map", "u16", "u16", size=1024)
program.add_map(port_map)
```

##### `add_function(function: BPFFunction) -> None`

Add BPF function.

```python
from source_query_proxy.ebpf import BPFFunction

func = BPFFunction(
    name="tc_ingress",
    return_type="int",
    parameters=[("struct __sk_buff *", "skb")],
    body="return TC_ACT_OK;"
)
program.add_function(func)
```

##### `apply_operation(operation: BPFOperation) -> None`

Apply high-level operation to program.

```python
from source_query_proxy.ebpf import PacketRedirectOperation

op = PacketRedirectOperation(
    server_port=27015,
    bind_port=27016
)
program.apply_operation(op)
```

##### `render() -> str`

Generate complete BPF C code.

```python
bpf_code = program.render()
print(bpf_code)
```

**Returns**: String containing BPF C code

#### BPFStruct

C struct definition.

```python
from source_query_proxy.ebpf import BPFStruct

struct = BPFStruct(
    name="redirect_key_t",
    fields=[
        ("u32", "ip"),
        ("u16", "port")
    ]
)
```

**Parameters**:
- `name` (str): Struct name
- `fields` (List[Tuple[str, str]]): List of (type, name) tuples

**Methods**:

##### `render() -> str`

Generate C struct definition.

```python
code = struct.render()
# Output:
# struct redirect_key_t {
#     u32 ip;
#     u16 port;
# } __attribute__((packed));
```

#### BPFMap

BPF hash map declaration.

```python
from source_query_proxy.ebpf import BPFMap

bpf_map = BPFMap(
    name="port_map",
    key_type="u16",
    value_type="u16",
    size=1024
)
```

**Parameters**:
- `name` (str): Map name
- `key_type` (str): C type for keys
- `value_type` (str): C type for values
- `size` (int): Maximum number of entries

**Methods**:

##### `render() -> str`

Generate BPF_HASH declaration.

```python
code = bpf_map.render()
# Output: BPF_HASH(port_map, u16, u16, 1024);
```

#### BPFFunction

BPF function definition.

```python
from source_query_proxy.ebpf import BPFFunction

func = BPFFunction(
    name="tc_ingress",
    return_type="int",
    parameters=[("struct __sk_buff *", "skb")],
    body="return TC_ACT_OK;"
)
```

**Parameters**:
- `name` (str): Function name
- `return_type` (str): C return type
- `parameters` (List[Tuple[str, str]]): List of (type, name) tuples
- `body` (str): Function body C code

**Methods**:

##### `render() -> str`

Generate function definition.

```python
code = func.render()
# Output:
# int tc_ingress(struct __sk_buff *skb) {
#     return TC_ACT_OK;
# }
```

#### PacketRedirectOperation

High-level packet redirection operation.

```python
from source_query_proxy.ebpf import PacketRedirectOperation

operation = PacketRedirectOperation(
    server_port=27015,
    bind_port=27016,
    bind_ip="192.168.1.100"  # Optional
)
```

**Parameters**:
- `server_port` (int): Game server port
- `bind_port` (int): sqproxy listen port
- `bind_ip` (str, optional): IP address for IP+port lookup

**Methods**:

##### `apply_to_program(program: BPFProgram) -> None`

Apply operation to program.

Adds:
- Redirect key struct
- Port/addr hash maps
- Ingress function (incoming packets)
- Egress function (outgoing packets)

```python
program = BPFProgram("redirect")
operation.apply_to_program(program)
code = program.render()
```

#### EBPFRedirector

Async lifecycle manager for eBPF redirection.

```python
from source_query_proxy.ebpf.redirector import EBPFRedirector

redirector = EBPFRedirector()
```

**Methods**:

##### `async start() -> None`

Start eBPF redirection.

```python
import asyncio

async def main():
    redirector = EBPFRedirector()
    await redirector.start()

asyncio.run(main())
```

Steps:
1. Generate BPF C code
2. Compile with BCC
3. Load functions (tc_ingress, tc_egress)
4. Populate BPF maps
5. Attach to traffic control

##### `async stop() -> None`

Stop eBPF redirection and cleanup.

```python
await redirector.stop()
```

Cleanup:
1. Detach from traffic control
2. Clear BPF maps
3. Unload BPF program

##### `async restart() -> None`

Restart eBPF redirection.

```python
await redirector.restart()
```

Equivalent to:
```python
await redirector.stop()
await redirector.start()
```

## Configuration

### source_query_proxy.config

Configuration loading and validation.

#### load_config

Load configuration from directories.

```python
from source_query_proxy.config import load_config

config = load_config()
```

**Returns**: Configuration dictionary

**Searches**:
- `/etc/sqproxy/conf.d/`
- `./conf.d/`

**File order**: Alphabetical (use numeric prefixes)

#### validate_config

Validate configuration.

```python
from source_query_proxy.config import validate_config

errors = validate_config(config)
if errors:
    print("Config errors:", errors)
```

**Parameters**:
- `config` (dict): Configuration dictionary

**Returns**: List of error messages (empty if valid)

## Protocol

### source_query_proxy.protocol

A2S protocol implementation.

#### A2S_INFO

Query server information.

```python
from source_query_proxy.protocol import A2S_INFO

request = A2S_INFO()
data = request.encode()
```

#### A2S_PLAYER

Query player list.

```python
from source_query_proxy.protocol import A2S_PLAYER

request = A2S_PLAYER()
data = request.encode()
```

#### A2S_RULES

Query server rules.

```python
from source_query_proxy.protocol import A2S_RULES

request = A2S_RULES()
data = request.encode()
```

## Proxy

### source_query_proxy.proxy

Main proxy logic.

#### QueryProxy

Proxy server for A2S queries.

```python
from source_query_proxy.proxy import QueryProxy

proxy = QueryProxy(
    server_ip="192.168.1.100",
    server_port=27015,
    bind_ip="0.0.0.0",
    bind_port=27016
)
```

**Methods**:

##### `async start() -> None`

Start proxy server.

```python
import asyncio

async def main():
    proxy = QueryProxy(...)
    await proxy.start()

asyncio.run(main())
```

##### `async stop() -> None`

Stop proxy server.

```python
await proxy.stop()
```

## CLI

### source_query_proxy.__main__

Command-line interface.

#### Commands

##### `sqproxy run`

Run sqproxy server.

```bash
sqproxy run
```

**Options**:
- `--config-dir PATH`: Configuration directory

##### `sqproxy config validate`

Validate configuration.

```bash
sqproxy config validate
```

##### `sqproxy config show`

Show parsed configuration.

```bash
sqproxy config show
```

**Options**:
- `--server NAME`: Show specific server

##### `sqproxy version`

Show version.

```bash
sqproxy version
```

## Examples

### Complete eBPF Example

```python
import asyncio
from source_query_proxy.ebpf import BPFProgram, PacketRedirectOperation
from source_query_proxy.ebpf.redirector import EBPFRedirector

async def main():
    # Generate BPF program
    program = BPFProgram("redirect")

    # Add packet redirect operation
    operation = PacketRedirectOperation(
        server_port=27015,
        bind_port=27016
    )
    operation.apply_to_program(program)

    # Render BPF C code
    bpf_code = program.render()
    print(f"Generated {len(bpf_code)} bytes of BPF code")

    # Start eBPF redirection
    redirector = EBPFRedirector()
    await redirector.start()

    print("eBPF redirection active")

    # Wait for signal
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass

    # Cleanup
    await redirector.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### Manual BPF Program Construction

```python
from source_query_proxy.ebpf import (
    BPFProgram, BPFStruct, BPFMap, BPFFunction
)

# Create program
program = BPFProgram("custom")

# Add includes
program.add_include("<uapi/linux/bpf.h>")
program.add_include("<uapi/linux/pkt_cls.h>")

# Add struct
key_struct = BPFStruct("key_t", [
    ("u32", "ip"),
    ("u16", "port")
])
program.add_struct(key_struct)

# Add map
my_map = BPFMap("my_map", "u16", "u32", size=512)
program.add_map(my_map)

# Add function
func = BPFFunction(
    name="my_handler",
    return_type="int",
    parameters=[("void *", "ctx")],
    body="""
    u16 key = 27015;
    u32 *value = my_map.lookup(&key);
    if (value) {
        return *value;
    }
    return 0;
    """
)
program.add_function(func)

# Generate code
code = program.render()
print(code)
```

## Type Definitions

### BPFElement

Base class for all BPF elements.

```python
class BPFElement:
    def render(self) -> str:
        """Render element to C code"""
        raise NotImplementedError
```

### BPFOperation

Base class for high-level operations.

```python
class BPFOperation:
    def apply_to_program(self, program: BPFProgram) -> None:
        """Apply operation to BPF program"""
        raise NotImplementedError
```

## See Also

- [Configuration Guide](configuration.md) - Config file reference
- [Development Guide](development.md) - Development workflow
- [eBPF Architecture](ebpf/architecture.md) - Implementation details
