"""
Runtime helpers for eBPF packet redirection

This module provides utility functions for:
- Network interface discovery
- Server configuration collection
- BPF program generation
- BPF map population
"""

import logging
import socket
import struct
from ipaddress import IPv4Address, ip_address
from typing import List, Optional, Tuple

import pyroute2

from .. import config

logger = logging.getLogger(__name__)

# Lazy import BCC to avoid import errors if not installed
_bcc_imported = False
_BPF = None


def import_bcc():
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


def get_addr_interface(addr: IPv4Address) -> Optional[str]:
    """Get network interface name for given IP address

    Args:
        addr: IPv4 address to find interface for

    Returns:
        Interface name or None if not found
    """
    with pyroute2.IPDB() as ipdb:
        for idx, addresses in ipdb.ipaddr.items():
            for ifaddr, _prefix in addresses:
                if ip_address(ifaddr) == addr:
                    return ipdb.by_index[idx]['ifname']
    return None


def get_default_interface() -> str:
    """Get default network interface

    Returns:
        Interface name

    Raises:
        config.ConfigurationError: If default interface cannot be determined
    """
    with pyroute2.IPRoute() as ipr:
        if default_routes := ipr.get_default_routes():
            idx = default_routes[0].get_attr('RTA_OIF')
            return ipr.get_links(idx)[0].get_attr('IFLA_IFNAME')
    raise config.ConfigurationError("Cannot determine default network interface")


def collect_server_mappings() -> Tuple[bool, str, List[Tuple[int, int, Optional[str]]]]:
    """Collect all server port mappings from config

    Returns:
        Tuple of (use_ipport_key, interface, mappings)
        - use_ipport_key: Whether to use IP+port lookup mode
        - interface: Network interface name
        - mappings: List of (server_port, bind_port, bind_ip_str) tuples

    Raises:
        config.ConfigurationError: If configuration is invalid
        RuntimeError: If no servers are configured
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
            server_interface = get_addr_interface(bind_ip)
            if server_interface is None:
                raise config.ConfigurationError(f"Can't get interface name for {bind_ip}")

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
        interface = get_default_interface()

    return use_ipport_key, interface, mappings


def generate_bpf_program(use_ipport_key: bool) -> str:
    """Generate BPF C code for packet redirection

    Args:
        use_ipport_key: If True, use IP+port lookup; otherwise port-only

    Returns:
        BPF C code as string
    """
    from . import BPFProgram, PacketRedirectOperation

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


def ip_to_int(ip_str: str) -> int:
    """Convert IP address string to integer (network byte order)

    Args:
        ip_str: IP address string (e.g., "192.168.1.1")

    Returns:
        Integer representation in network byte order
    """
    return struct.unpack("!I", socket.inet_aton(ip_str))[0]


def populate_maps(bpf, use_ipport_key: bool, mappings: List[Tuple[int, int, Optional[str]]]) -> None:
    """Populate BPF maps with port mappings

    Args:
        bpf: BCC BPF instance
        use_ipport_key: Whether to use IP+port or port-only map
        mappings: List of (server_port, bind_port, bind_ip) tuples

    Raises:
        Exception: If map population fails (original exception preserved)
    """
    import traceback

    try:
        if use_ipport_key:
            addr_map = bpf.get_table("addr_map")

            for server_port, bind_port, bind_ip in mappings:
                if bind_ip is None:
                    logger.warning(
                        f"Skipping {server_port}:{bind_port} - no IP for IP+port mode"
                    )
                    continue

                try:
                    ip_int = ip_to_int(bind_ip)
                    key = addr_map.Key(ip_int, server_port)
                    addr_map[key] = bind_port
                    logger.info(f"  Map: ({bind_ip}:{server_port}) -> {bind_port}")
                except Exception as e:
                    logger.error(
                        f"Failed to populate addr_map for {bind_ip}:{server_port}:\n{traceback.format_exc()}"
                    )
                    raise
        else:
            port_map = bpf.get_table("port_map")

            for server_port, bind_port, bind_ip in mappings:
                try:
                    port_map[server_port] = bind_port
                    logger.info(f"  Map: {server_port} -> {bind_port}")
                except Exception as e:
                    logger.error(
                        f"Failed to populate port_map for {server_port}:\n{traceback.format_exc()}"
                    )
                    raise
    except Exception:
        logger.error(f"Error populating BPF maps:\n{traceback.format_exc()}")
        raise
