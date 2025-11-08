"""
eBPF packet redirection lifecycle manager

Provides the EBPFRedirector class for managing the complete lifecycle
of eBPF-based packet redirection with async/await support.
"""

import logging
from typing import Optional

import pyroute2

from .runtime import collect_server_mappings, generate_bpf_program, import_bcc, populate_maps
from .tc import attach_tc_bpf, cleanup_tc

logger = logging.getLogger(__name__)


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
            BPF = import_bcc()

            # Collect server configurations
            logger.info("Collecting server configurations...")
            use_ipport_key, interface, mappings = collect_server_mappings()
            self._interface = interface

            logger.info(f"Mode: {'IP+port' if use_ipport_key else 'port-only'}")
            logger.info(f"Interface: {interface}")
            logger.info(f"Servers: {len(mappings)}")

            # Generate BPF program
            logger.info("Generating BPF C code...")
            bpf_code = generate_bpf_program(use_ipport_key)
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
            populate_maps(self._bpf, use_ipport_key, mappings)
            logger.info(f"✓ Populated {len(mappings)} port mappings")

            # Create IPRoute instance for tc operations
            self._ipr = pyroute2.IPRoute()

            # Attach to tc
            logger.info(f"Attaching BPF programs to interface {interface}...")
            try:
                self._ifindex, self._fn_incoming, self._fn_outgoing = attach_tc_bpf(
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

        except (RuntimeError, ValueError, OSError) as exc:
            # Cleanup on failure, ensuring both exceptions are visible
            try:
                await self._cleanup()
            except Exception as cleanup_exc:
                logger.error(f"Exception during cleanup after error: {cleanup_exc}", exc_info=True)
                # Chain the exceptions for full visibility
                raise exc from cleanup_exc
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
                cleanup_tc(self._ipr, self._ifindex, safe=True)
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
