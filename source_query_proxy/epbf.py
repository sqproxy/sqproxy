"""
eBPF packet redirection using template engine and BCC

Replaces external sqredirect dependency with internal BPF code generation.
"""

import asyncio
import logging
import socket
import struct
from ipaddress import IPv4Address, ip_address
from typing import List, Optional, Tuple

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


def _get_addr_interface(addr: IPv4Address) -> Optional[str]:
    """Get network interface name for given IP address"""
    with pyroute2.IPDB() as ipdb:
        for idx, addresses in ipdb.ipaddr.items():
            for ifaddr, _prefix in addresses:
                if ip_address(ifaddr) == addr:
                    return ipdb.by_index[idx]['ifname']
    return None


def _get_default_interface() -> str:
    """Get default network interface"""
    with pyroute2.IPRoute() as ipr:
        if default_routes := ipr.get_default_routes():
            idx = default_routes[0].get_attr('RTA_OIF')
            return ipr.get_links(idx)[0].get_attr('IFLA_IFNAME')
    raise config.ConfigurationError("Cannot determine default network interface")


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


def _populate_maps(bpf, use_ipport_key: bool, mappings: List[Tuple[int, int, Optional[str]]]) -> None:
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
                    ip_int = _ip_to_int(bind_ip)
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


def _rollback_tc_bpf(ipr, ifindex: int, ingress_added: bool, ingress_filter_added: bool, sfq_added: bool) -> None:
    """Rollback partial tc attachment state on failure

    Args:
        ipr: pyroute2 IPRoute instance
        ifindex: Interface index
        ingress_added: Whether ingress qdisc was added
        ingress_filter_added: Whether ingress filter was added
        sfq_added: Whether sfq qdisc was added
    """
    # Clean up in reverse order of creation
    if sfq_added:
        try:
            ipr.tc("del", "sfq", ifindex, "1:")
            logger.debug("Rolled back sfq qdisc")
        except Exception as cleanup_e:
            logger.warning(f"Failed to rollback sfq qdisc: {cleanup_e}")

    if ingress_filter_added:
        try:
            ipr.tc("del-filter", "u32", ifindex, ":1", parent="ffff:")
            logger.debug("Rolled back ingress filter")
        except Exception as cleanup_e:
            logger.warning(f"Failed to rollback ingress filter: {cleanup_e}")

    if ingress_added:
        try:
            ipr.tc("del", "ingress", ifindex, "ffff:")
            logger.debug("Rolled back ingress qdisc")
        except Exception as cleanup_e:
            logger.warning(f"Failed to rollback ingress qdisc: {cleanup_e}")


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

    Raises:
        RuntimeError: If setup fails, with automatic rollback of partial state
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

    # Track what we've added for rollback on failure
    ingress_added = False
    ingress_filter_added = False
    sfq_added = False

    try:
        # Setup incoming traffic hook (ingress qdisc)
        try:
            ipr.tc("add", "ingress", ifindex, "ffff:")
            ingress_added = True
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
        ingress_filter_added = True
        logger.info(f"✓ Attached incoming BPF filter to {interface} (ingress)")

        # Setup outgoing traffic hook (sfq qdisc)
        try:
            ipr.tc("add", "sfq", ifindex, "1:")
            sfq_added = True
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

    except Exception as e:
        # Rollback partial state on failure
        logger.error(f"Failed to attach tc bpf, rolling back partial state: {e}")
        _rollback_tc_bpf(ipr, ifindex, ingress_added, ingress_filter_added, sfq_added)
        raise RuntimeError("Failed to attach tc bpf, partial state rolled back") from e


def _cleanup_tc(ipr, ifindex: int, safe: bool = False) -> None:
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
        # Only ignore if safe mode and qdisc doesn't exist
        if not (safe and exc.args[1] == 'Invalid argument'):
            logger.error(f"Failed to remove ingress qdisc: {exc}")
            if not safe:
                raise

    try:
        ipr.tc("del", "sfq", ifindex, "1:")
        logger.debug("Removed sfq qdisc")
    except NetlinkError as exc:
        # Only ignore if safe mode and qdisc doesn't exist
        if not (safe and exc.args[1] == 'Invalid argument'):
            logger.error(f"Failed to remove sfq qdisc: {exc}")
            if not safe:
                raise


class EBPFRedirector:
    """Async lifecycle manager for eBPF packet redirection

    Manages the complete lifecycle of eBPF-based packet redirection:
    - Compiles BPF programs using the template engine
    - Attaches programs to network interfaces via tc
    - Populates BPF maps with port mappings
    - Handles cleanup and resource management
    - Supports start/stop/restart for dynamic reconfiguration

    Usage:
        # As async context manager
        async with EBPFRedirector() as redirector:
            # eBPF is active
            await asyncio.sleep(3600)
        # Automatic cleanup on exit

        # Or manual lifecycle management
        redirector = EBPFRedirector()
        await redirector.start()
        # ... later ...
        await redirector.restart()  # Reload config
        # ... later ...
        await redirector.stop()
    """

    def __init__(self):
        """Initialize eBPF redirector (does not start redirection)"""
        self._bpf = None
        self._ipr = None
        self._ifindex: Optional[int] = None
        self._fn_incoming = None
        self._fn_outgoing = None
        self._interface: Optional[str] = None
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if eBPF redirection is currently active"""
        return self._running

    @property
    def interface(self) -> Optional[str]:
        """Get the network interface being used"""
        return self._interface

    async def start(self):
        """Start eBPF packet redirection

        Raises:
            RuntimeError: If already running or if start fails
            config.ConfigurationError: If configuration is invalid
        """
        if self._running:
            raise RuntimeError("eBPF redirection is already running")

        logger.info("=== Starting eBPF packet redirection ===")

        try:
            BPF = _import_bcc()

            # Collect server configurations
            logger.info("Collecting server configurations...")
            use_ipport_key, interface, mappings = _collect_server_mappings()
            self._interface = interface

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
                self._bpf = BPF(text=bpf_code, debug=0)
            except Exception as e:
                logger.error(f"BPF compilation failed: {e}")
                logger.debug(f"Generated BPF code:\n{bpf_code}")
                raise RuntimeError(f"BPF compilation failed: {e}") from e

            logger.info("✓ BPF program compiled successfully")

            # Populate maps with port mappings
            logger.info("Populating BPF maps...")
            _populate_maps(self._bpf, use_ipport_key, mappings)
            logger.info(f"✓ Populated {len(mappings)} port mappings")

            # Create IPRoute instance for tc operations
            self._ipr = pyroute2.IPRoute()

            # Attach to tc
            logger.info(f"Attaching BPF programs to interface {interface}...")
            try:
                self._ifindex, self._fn_incoming, self._fn_outgoing = _attach_tc_bpf(
                    interface, self._bpf, self._ipr
                )
            except Exception as e:
                logger.error(f"Failed to attach BPF programs: {e}")
                self._ipr.close()
                self._ipr = None
                raise RuntimeError(f"tc attachment failed: {e}") from e

            logger.info("✓ BPF programs attached successfully")
            logger.info("=== eBPF redirection is active ===")

            self._running = True

        except Exception:
            # Cleanup on failure
            await self._cleanup()
            raise

    async def stop(self):
        """Stop eBPF packet redirection and cleanup resources

        Safe to call multiple times (idempotent).
        """
        if not self._running:
            logger.debug("eBPF redirection is not running, skipping stop")
            return

        logger.info("Stopping eBPF redirection...")
        self._running = False
        await self._cleanup()
        logger.info("✓ eBPF redirection stopped")

    async def restart(self):
        """Restart eBPF redirection (stop then start)

        Useful for reloading configuration changes on the fly.

        Raises:
            RuntimeError: If restart fails
            config.ConfigurationError: If new configuration is invalid
        """
        logger.info("Restarting eBPF redirection...")
        await self.stop()
        await self.start()
        logger.info("✓ eBPF redirection restarted")

    async def _cleanup(self):
        """Internal cleanup method - idempotent and async-safe"""
        if self._ipr is None:
            return

        logger.debug("Cleaning up tc qdiscs and resources...")

        try:
            if self._ifindex is not None:
                _cleanup_tc(self._ipr, self._ifindex, safe=True)
        finally:
            # Always close IPRoute
            try:
                self._ipr.close()
            except Exception as e:
                logger.warning(f"Error closing IPRoute: {e}")
            finally:
                self._ipr = None
                self._ifindex = None
                self._fn_incoming = None
                self._fn_outgoing = None
                self._bpf = None
                self._interface = None

        logger.debug("✓ Cleanup complete")

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop()
        return False


async def run_ebpf_redirection():
    """Main entry point for eBPF redirection (legacy compatibility)

    This function provides backward compatibility with the old interface.
    It runs eBPF redirection until interrupted (Ctrl+C or signal).

    For new code, prefer using EBPFRedirector class directly for better
    control over lifecycle and support for restart/reload operations.

    Example migration:
        # Old way (this function)
        await run_ebpf_redirection()

        # New way (recommended)
        async with EBPFRedirector() as redirector:
            # Your application logic here
            await asyncio.Event().wait()  # Wait forever
    """
    import signal

    redirector = EBPFRedirector()

    # Signal handler for graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()

    # Register signal handlers (let application handle SIGTERM/SIGINT)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Start eBPF redirection
        await redirector.start()

        logger.info("Press Ctrl+C to stop")

        # Wait for shutdown signal
        await shutdown_event.wait()

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down eBPF redirection...")
    except Exception as e:
        logger.error(f"Unexpected error in redirection: {e}")
        raise
    finally:
        # Always cleanup
        await redirector.stop()


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
