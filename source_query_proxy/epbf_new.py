"""
eBPF packet redirection using class-based template engine and BCC

Replaces external sqredirect dependency with internal BPF code generation.
"""

import asyncio
import logging
from ipaddress import IPv4Address, ip_address
from typing import Dict, Tuple

import pyroute2
from bcc import BPF

from . import config
from .ebpf import BPFProgram, PacketRedirectOperation

logger = logging.getLogger(__name__)


def _get_addr_interface(addr: IPv4Address):
    """Get network interface name for given IP address"""
    ipdb = pyroute2.IPDB()
    for idx, addresses in ipdb.ipaddr.items():
        for ifaddr, _prefix in addresses:
            if ip_address(ifaddr) == addr:
                return ipdb.by_index[idx]['ifname']
    return None


def generate_redirect_programs() -> Dict[str, Tuple[str, int, int, str]]:
    """Generate BPF programs for all configured servers

    Returns:
        Dict mapping server_name to (bpf_c_code, server_port, bind_port, bind_ip)
    """
    programs = {}

    for server_name, server in config.settings.servers:
        if server.network.ebpf_no_redirect:
            logger.info(f"Skip eBPF redirect for {server_name} (ebpf_no_redirect=true)")
            continue

        bind_ip = server.network.bind_ip
        server_port = server.network.server_port
        bind_port = server.network.bind_port

        # Generate BPF program
        program = BPFProgram(f"redirect_{server_name}")

        # Determine if we need IP+port lookup
        use_ipport_key = str(bind_ip) != '0.0.0.0'
        bind_ip_str = None if str(bind_ip) == '0.0.0.0' else str(bind_ip)

        op = PacketRedirectOperation(
            server_port=server_port,
            bind_port=bind_port,
            bind_ip=bind_ip_str,
            use_ipport_key=use_ipport_key
        )
        program.apply_operation(op)

        bpf_code = program.render()
        programs[server_name] = (bpf_code, server_port, bind_port, bind_ip_str)

        logger.debug(f"Generated BPF program for {server_name}: {server_port} -> {bind_port}")

    return programs


def load_and_attach_bpf(
    interface: str,
    bpf_code: str,
    server_port: int,
    bind_port: int,
    bind_ip: str = None
) -> BPF:
    """Compile and attach BPF program to network interface

    Args:
        interface: Network interface name (e.g., "eth0")
        bpf_code: Generated BPF C code
        server_port: Server port to redirect from
        bind_port: Bind port to redirect to
        bind_ip: Optional bind IP address

    Returns:
        BPF instance with loaded programs

    Raises:
        RuntimeError: If compilation or attachment fails
    """
    logger.info(f"Compiling BPF program for {server_port} -> {bind_port} on {interface}")

    try:
        # Compile BPF program
        b = BPF(text=bpf_code, debug=0)

        # Load functions
        fn_incoming = b.load_func("incoming", BPF.SCHED_CLS)
        fn_outgoing = b.load_func("outgoing", BPF.SCHED_CLS)

        # Get network interface using pyroute2
        ip = pyroute2.IPRoute()

        # Get interface index
        idx = ip.link_lookup(ifname=interface)[0]

        # Remove any existing qdisc (ignore errors)
        try:
            ip.tc("del", "clsact", idx)
        except Exception:
            pass

        # Add clsact qdisc (allows attaching tc BPF programs)
        ip.tc("add", "clsact", idx)

        # Attach incoming filter (ingress)
        # Packets arriving at server_port are redirected to bind_port
        ip.tc(
            "add-filter",
            "bpf",
            idx,
            ":1",
            fd=fn_incoming.fd,
            name=fn_incoming.name,
            parent="ffff:fff2",  # ingress
            classid=1,
            direct_action=True,
        )

        # Attach outgoing filter (egress)
        # Packets leaving bind_port get source port rewritten to server_port
        ip.tc(
            "add-filter",
            "bpf",
            idx,
            ":1",
            fd=fn_outgoing.fd,
            name=fn_outgoing.name,
            parent="ffff:fff3",  # egress
            classid=1,
            direct_action=True,
        )

        logger.info(f"✓ Attached BPF programs to {interface}")

        # Populate map with port mappings
        if bind_ip:
            # Use IP+port map
            addr_map = b.get_table("addr_map")

            # Convert IP to int (network byte order)
            import socket
            import struct
            ip_int = struct.unpack("!I", socket.inet_aton(bind_ip))[0]

            # Map: (ip, server_port) -> bind_port
            key = addr_map.Key(ip_int, server_port)
            addr_map[key] = bind_port

            logger.info(f"  Map: ({bind_ip}:{server_port}) -> {bind_port}")
        else:
            # Use port-only map
            port_map = b.get_table("port_map")

            # Map: server_port -> bind_port
            port_map[server_port] = bind_port

            logger.info(f"  Map: {server_port} -> {bind_port}")

        return b

    except Exception as e:
        logger.error(f"Failed to load BPF program: {e}")
        raise RuntimeError(f"BPF load failed: {e}") from e


async def run_ebpf_redirection():
    """Main entry point for eBPF redirection

    Generates BPF programs for all configured servers and attaches them
    to the network interface.
    """
    logger.info("Starting eBPF packet redirection with template engine")

    # Generate programs for all servers
    programs = generate_redirect_programs()

    if not programs:
        logger.warning("No servers configured for eBPF redirection")
        return

    # Determine network interface
    # All servers must use the same interface (validated below)
    interface = None
    is_wide = False

    for server_name, server in config.settings.servers:
        if server.network.ebpf_no_redirect:
            continue

        bind_ip = server.network.bind_ip

        if str(bind_ip) == '0.0.0.0':
            server_interface = None
            is_wide = True
        else:
            server_interface = _get_addr_interface(bind_ip)
            if server_interface is None:
                raise AssertionError(f"Can't get interface name for {bind_ip}")

        if interface is None:
            interface = server_interface

        if server_interface != interface:
            raise config.ConfigurationError(
                f'Different interfaces not supported yet: {server_interface} != {interface}'
            )

    if is_wide:
        logger.warning(
            "Wide interface binding (0.0.0.0) detected. "
            "Will use default interface. This may not work correctly."
        )
        # Try to get default interface
        if interface is None:
            ip = pyroute2.IPRoute()
            default_routes = ip.get_default_routes()
            if default_routes:
                idx = default_routes[0].get_attr('RTA_OIF')
                interface = ip.get_links(idx)[0].get_attr('IFLA_IFNAME')
            else:
                raise RuntimeError("Cannot determine default network interface")

    logger.info(f"Using network interface: {interface}")

    # Load and attach all programs
    bpf_instances = []
    for server_name, (bpf_code, server_port, bind_port, bind_ip) in programs.items():
        try:
            b = load_and_attach_bpf(interface, bpf_code, server_port, bind_port, bind_ip)
            bpf_instances.append((server_name, b))
        except Exception as e:
            logger.error(f"Failed to load BPF for {server_name}: {e}")
            # Clean up any already loaded programs
            for _, prev_b in bpf_instances:
                prev_b.cleanup()
            raise

    logger.info(f"✓ Successfully loaded {len(bpf_instances)} BPF programs")
    logger.info("eBPF redirection is active. Press Ctrl+C to stop.")

    # Keep the programs loaded (they'll be unloaded when the process exits)
    # In production, this would run as a daemon
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down eBPF redirection...")
        for server_name, b in bpf_instances:
            logger.info(f"Cleaning up {server_name}")
            b.cleanup()
        logger.info("eBPF redirection stopped")
