"""
eBPF packet redirection - Main entry point

This module provides the main entry point for eBPF-based packet redirection.
The implementation has been split into smaller modules for better maintainability:

- ebpf/runtime.py: Network helpers, BPF generation, and map population
- ebpf/tc.py: Traffic control (tc) operations
- ebpf/redirector.py: EBPFRedirector lifecycle manager

For new code, use EBPFRedirector class directly:
    from source_query_proxy.ebpf.redirector import EBPFRedirector

    async with EBPFRedirector() as redirector:
        # eBPF is active
        await asyncio.Event().wait()
"""

import asyncio
import logging
import signal

from .ebpf.redirector import EBPFRedirector
from .ebpf.runtime import collect_server_mappings

logger = logging.getLogger(__name__)


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
    redirector = EBPFRedirector()
    loop = asyncio.get_running_loop()

    # Signal handler for graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal, shutting down...")
        shutdown_event.set()

    # Register signal handlers using asyncio (async-safe)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)
    loop.add_signal_handler(signal.SIGINT, signal_handler)

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
        # Remove signal handlers
        loop.remove_signal_handler(signal.SIGTERM)
        loop.remove_signal_handler(signal.SIGINT)
        # Always cleanup
        await redirector.stop()


# Backward compatibility: keep get_ebpf_program_run_args for tests
def get_ebpf_program_run_args():
    """Legacy function for backward compatibility with tests

    This function is deprecated and will be removed in the future.

    Returns:
        List of server mapping arguments

    Raises:
        RuntimeError: If server mappings collection fails
    """
    logger.warning("get_ebpf_program_run_args() is deprecated")

    # Collect mappings using new logic
    try:
        use_ipport_key, interface, mappings = collect_server_mappings()
    except Exception as e:
        logger.error(f"Failed to collect server mappings: {e}", exc_info=True)
        raise RuntimeError("Failed to collect eBPF program arguments") from e

    args = []
    for server_port, bind_port, bind_ip in mappings:
        if bind_ip:
            arg = f'{bind_ip}:{server_port}:{bind_port}'
        else:
            arg = f'{server_port}:{bind_port}'
        args.append(arg)

    return args


# Re-export for backward compatibility
__all__ = ['EBPFRedirector', 'run_ebpf_redirection', 'get_ebpf_program_run_args']
