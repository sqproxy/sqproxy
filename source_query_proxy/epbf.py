"""
eBPF packet redirection using template engine and BCC

Replaces external sqredirect dependency with internal BPF code generation.
"""

import asyncio
import logging
import socket
import struct
from ipaddress import IPv4Address, ip_address
from typing import List, Tuple

import pyroute2

from . import config

logger = logging.getLogger(__name__)

# Lazy import BCC to avoid import errors if not installed
_bcc_imported = False
_BPF = None


def _import_bcc():
    """Lazy import of BCC to provide better error messages"""
    global _bcc_imported, _BPF
    if not _bcc_imported:
        try:
            from bcc import BPF as _BPF_class

            _BPF = _BPF_class
            _bcc_imported = True
        except ImportError as e:
            raise RuntimeError(
                "BCC (BPF Compiler Collection) is not installed. "
                "Install it with: apt-get install python3-bpfcc"
            ) from e
    return _BPF


def _get_addr_interface(addr: IPv4Address):
    """Get network interface name for given IP address"""
    ipdb = pyroute2.IPDB()
    for idx, addresses in ipdb.ipaddr.items():
        for ifaddr, _prefix in addresses:
            if ip_address(ifaddr) == addr:
                return ipdb.by_index[idx]['ifname']
    return None


def _get_default_interface():
    """Get default network interface"""
    ip = pyroute2.IPRoute()
    default_routes = ip.get_default_routes()
    if default_routes:
        idx = default_routes[0].get_attr('RTA_OIF')
        interface = ip.get_links(idx)[0].get_attr('IFLA_IFNAME')
        return interface
    raise RuntimeError("Cannot determine default network interface")


def _collect_server_mappings() -> Tuple[bool, str, List[Tuple[int, int, str]]]:
    """Collect all server port mappings from config

    Returns:
        (use_ipport_key, interface, [(server_port, bind_port, bind_ip), ...])
    """
    mappings = []
    interface = None
    use_ipport_key = False

    for server_name, server in config.settings.servers:
        if server.network.ebpf_no_redirect:
            logger.info(f"Skip eBPF redirect for {server_name} (ebpf_no_redirect=true)")
            continue

        bind_ip = server.network.bind_ip
        server_port = server.network.server_port
        bind_port = server.network.bind_port

        # Determine interface
        if str(bind_ip) == '0.0.0.0':
            server_interface = None
        else:
            use_ipport_key = True  # Need IP+port lookup
            server_interface = _get_addr_interface(bind_ip)
            if server_interface is None:
                raise AssertionError(f"Can't get interface name for {bind_ip}")

        if interface is None:
            interface = server_interface

        if server_interface != interface:
            raise config.ConfigurationError(
                f'Different interfaces not supported yet: {server_interface} != {interface}'
            )

        bind_ip_str = None if str(bind_ip) == '0.0.0.0' else str(bind_ip)
        mappings.append((server_port, bind_port, bind_ip_str))

        logger.debug(f"Server {server_name}: {server_port} -> {bind_port} (ip={bind_ip_str})")

    if not mappings:
        raise RuntimeError("No servers configured for eBPF redirection")

    # If no interface determined, use default
    if interface is None:
        logger.warning(
            "Wide interface binding (0.0.0.0) detected. Using default interface."
        )
        interface = _get_default_interface()

    return use_ipport_key, interface, mappings


def _generate_bpf_program(use_ipport_key: bool) -> str:
    """Generate BPF C code for packet redirection

    Args:
        use_ipport_key: If True, use IP+port lookup; otherwise port-only

    Returns:
        BPF C code as string
    """
    from .ebpf import BPFProgram, PacketRedirectOperation

    program = BPFProgram("sqproxy_redirect")

    # Create single redirect operation
    # We'll populate the maps manually after compilation
    op = PacketRedirectOperation(
        server_port=0,  # Dummy, we populate map later
        bind_port=0,  # Dummy, we populate map later
        use_ipport_key=use_ipport_key,
    )
    program.apply_operation(op)

    return program.render()


def _ip_to_int(ip_str: str) -> int:
    """Convert IP address string to integer (network byte order)"""
    return struct.unpack("!I", socket.inet_aton(ip_str))[0]


def _populate_maps(bpf, use_ipport_key: bool, mappings: List[Tuple[int, int, str]]):
    """Populate BPF maps with port mappings

    Args:
        bpf: BCC BPF instance
        use_ipport_key: Whether to use IP+port or port-only map
        mappings: List of (server_port, bind_port, bind_ip) tuples
    """
    if use_ipport_key:
        addr_map = bpf.get_table("addr_map")

        for server_port, bind_port, bind_ip in mappings:
            if bind_ip is None:
                logger.warning(
                    f"Skipping {server_port}:{bind_port} - no IP for IP+port mode"
                )
                continue

            ip_int = _ip_to_int(bind_ip)
            key = addr_map.Key(ip_int, server_port)
            addr_map[key] = bind_port

            logger.info(f"  Map: ({bind_ip}:{server_port}) -> {bind_port}")
    else:
        port_map = bpf.get_table("port_map")

        for server_port, bind_port, bind_ip in mappings:
            port_map[server_port] = bind_port
            logger.info(f"  Map: {server_port} -> {bind_port}")


def _attach_tc_bpf(interface: str, bpf, ipr) -> Tuple[int, any, any]:
    """Attach BPF programs to tc (traffic control)

    Uses the same approach as sqredirect:
    - ingress qdisc for incoming traffic
    - sfq qdisc for outgoing traffic
    - u32 filters with BPF actions

    Args:
        interface: Network interface name
        bpf: BCC BPF instance with compiled programs
        ipr: pyroute2 IPRoute instance

    Returns:
        (ifindex, fn_incoming, fn_outgoing) for cleanup
    """
    from pyroute2.netlink.exceptions import NetlinkError
    from pyroute2.netlink.rtnl import protocols

    BPF = _import_bcc()

    # Load BPF functions (SCHED_ACT mode like sqredirect)
    fn_incoming = bpf.load_func("incoming", BPF.SCHED_ACT)
    fn_outgoing = bpf.load_func("outgoing", BPF.SCHED_ACT)

    logger.info(f"Loaded BPF functions: incoming={fn_incoming.name}, outgoing={fn_outgoing.name}")

    # Get interface index
    ifindex = ipr.link_lookup(ifname=interface)[0]
    logger.debug(f"Interface {interface} has index {ifindex}")

    # Setup incoming traffic hook (ingress qdisc)
    try:
        ipr.tc("add", "ingress", ifindex, "ffff:")
        logger.debug("Added ingress qdisc")
    except NetlinkError as exc:
        if exc.args[1] != 'File exists':
            raise
        logger.debug("Ingress qdisc already exists")

    # Attach incoming BPF filter
    action_incoming = {
        "kind": "bpf",
        "fd": fn_incoming.fd,
        "name": fn_incoming.name,
        "action": "ok",
    }
    ipr.tc(
        "add-filter",
        "u32",
        ifindex,
        ":1",
        parent="ffff:",
        action=[action_incoming],
        protocol=protocols.ETH_P_ALL,
        target=0x10000,
        keys=["0x0/0x0+0"],
    )
    logger.info(f"✓ Attached incoming BPF filter to {interface} (ingress)")

    # Setup outgoing traffic hook (sfq qdisc)
    try:
        ipr.tc("add", "sfq", ifindex, "1:")
        logger.debug("Added sfq qdisc")
    except NetlinkError as exc:
        if exc.args[1] != 'File exists':
            raise
        logger.debug("SFQ qdisc already exists")

    # Attach outgoing BPF filter
    action_outgoing = {
        "kind": "bpf",
        "fd": fn_outgoing.fd,
        "name": fn_outgoing.name,
        "action": "ok",
    }
    ipr.tc(
        "add-filter",
        "u32",
        ifindex,
        ":2",
        parent="1:",
        action=[action_outgoing],
        target=0x10000,
        keys=["0x0/0x0+0"],
    )
    logger.info(f"✓ Attached outgoing BPF filter to {interface} (egress)")

    return ifindex, fn_incoming, fn_outgoing


def _cleanup_tc(ipr, ifindex: int, safe: bool = False):
    """Cleanup tc qdiscs

    Args:
        ipr: pyroute2 IPRoute instance
        ifindex: Interface index
        safe: If True, ignore 'Invalid argument' errors
    """
    from pyroute2.netlink.exceptions import NetlinkError

    try:
        ipr.tc("del", "ingress", ifindex, "ffff:")
        logger.debug("Removed ingress qdisc")
    except NetlinkError as exc:
        if not safe or exc.args[1] != 'Invalid argument':
            logger.error(f"Failed to remove ingress qdisc: {exc}")
            if not safe:
                raise

    try:
        ipr.tc("del", "sfq", ifindex, "1:")
        logger.debug("Removed sfq qdisc")
    except NetlinkError as exc:
        if not safe or exc.args[1] != 'Invalid argument':
            logger.error(f"Failed to remove sfq qdisc: {exc}")
            if not safe:
                raise


async def run_ebpf_redirection():
    """Main entry point for eBPF redirection

    Generates BPF program, compiles it, attaches to network interface,
    and keeps it running. Registers cleanup handlers for graceful shutdown.
    """
    import atexit
    import signal

    logger.info("=== Starting eBPF packet redirection ===")

    BPF = _import_bcc()

    # Collect server configurations
    logger.info("Collecting server configurations...")
    use_ipport_key, interface, mappings = _collect_server_mappings()

    logger.info(f"Mode: {'IP+port' if use_ipport_key else 'port-only'}")
    logger.info(f"Interface: {interface}")
    logger.info(f"Servers: {len(mappings)}")

    # Generate BPF program
    logger.info("Generating BPF C code...")
    bpf_code = _generate_bpf_program(use_ipport_key)
    logger.debug(f"Generated {len(bpf_code)} bytes of BPF C code")

    # Compile BPF program
    logger.info("Compiling BPF program with BCC...")
    try:
        bpf = BPF(text=bpf_code, debug=0)
    except Exception as e:
        logger.error(f"BPF compilation failed: {e}")
        logger.debug(f"Generated BPF code:\n{bpf_code}")
        raise RuntimeError(f"BPF compilation failed: {e}") from e

    logger.info("✓ BPF program compiled successfully")

    # Populate maps with port mappings
    logger.info("Populating BPF maps...")
    _populate_maps(bpf, use_ipport_key, mappings)
    logger.info(f"✓ Populated {len(mappings)} port mappings")

    # Create IPRoute instance for tc operations
    ipr = pyroute2.IPRoute()

    # Attach to tc
    logger.info(f"Attaching BPF programs to interface {interface}...")
    try:
        ifindex, fn_incoming, fn_outgoing = _attach_tc_bpf(interface, bpf, ipr)
    except Exception as e:
        logger.error(f"Failed to attach BPF programs: {e}")
        ipr.close()
        raise RuntimeError(f"tc attachment failed: {e}") from e

    logger.info("✓ BPF programs attached successfully")

    # Register cleanup handlers
    def cleanup_handler():
        logger.info("Cleaning up tc qdiscs...")
        _cleanup_tc(ipr, ifindex, safe=True)
        ipr.close()
        logger.info("✓ Cleanup complete")

    atexit.register(cleanup_handler)

    # Register signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        cleanup_handler()
        import sys
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("=== eBPF redirection is active ===")
    logger.info("Press Ctrl+C to stop")

    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down eBPF redirection...")
        # Cleanup happens via atexit
        logger.info("eBPF redirection stopped")


# Backward compatibility: keep get_ebpf_program_run_args for tests
def get_ebpf_program_run_args():
    """Legacy function for backward compatibility with tests

    This function is deprecated and will be removed in the future.
    """
    logger.warning("get_ebpf_program_run_args() is deprecated")

    # Collect mappings using new logic
    try:
        use_ipport_key, interface, mappings = _collect_server_mappings()
    except Exception:
        return []

    args = []
    for server_port, bind_port, bind_ip in mappings:
        if bind_ip:
            arg = f'{bind_ip}:{server_port}:{bind_port}'
        else:
            arg = f'{server_port}:{bind_port}'
        args += ['-p', arg]

    if interface:
        args += ['-i', interface]

    return args
