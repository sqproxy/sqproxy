"""
Traffic Control (tc) operations for eBPF

This module handles:
- Attaching BPF programs to network interfaces via tc
- Rollback on attachment failures
- Cleanup of tc qdiscs and filters
"""

import logging
from typing import Any, Tuple

from .runtime import import_bcc

logger = logging.getLogger(__name__)


def rollback_tc_bpf(ipr: Any, ifindex: int, ingress_added: bool, ingress_filter_added: bool, sfq_added: bool) -> None:
    """Rollback partial tc attachment state on failure

    Args:
        ipr: pyroute2 IPRoute instance
        ifindex: Interface index
        ingress_added: Whether ingress qdisc was added
        ingress_filter_added: Whether ingress filter was added
        sfq_added: Whether sfq qdisc was added

    Note:
        All rollback steps are attempted independently. If multiple steps fail,
        all errors are logged individually.
    """
    # Collect errors from all rollback steps
    errors = []

    # Clean up in reverse order of creation
    if sfq_added:
        try:
            ipr.tc("del", "sfq", ifindex, "1:")
            logger.debug("Rolled back sfq qdisc")
        except Exception as cleanup_e:
            errors.append(f"sfq qdisc: {cleanup_e}")
            logger.warning(f"Failed to rollback sfq qdisc: {cleanup_e}")

    if ingress_filter_added:
        try:
            ipr.tc("del-filter", "u32", ifindex, ":1", parent="ffff:")
            logger.debug("Rolled back ingress filter")
        except Exception as cleanup_e:
            errors.append(f"ingress filter: {cleanup_e}")
            logger.warning(f"Failed to rollback ingress filter: {cleanup_e}")

    if ingress_added:
        try:
            ipr.tc("del", "ingress", ifindex, "ffff:")
            logger.debug("Rolled back ingress qdisc")
        except Exception as cleanup_e:
            errors.append(f"ingress qdisc: {cleanup_e}")
            logger.warning(f"Failed to rollback ingress qdisc: {cleanup_e}")

    # Log summary if there were errors
    if errors:
        logger.error(f"Rollback encountered {len(errors)} error(s): {'; '.join(errors)}")


def attach_tc_bpf(interface: str, bpf: Any, ipr: Any) -> Tuple[int, Any, Any]:
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
        Tuple of (ifindex, fn_incoming, fn_outgoing) for cleanup

    Raises:
        RuntimeError: If setup fails, with automatic rollback of partial state
    """
    from pyroute2.netlink.exceptions import NetlinkError
    from pyroute2.netlink.rtnl import protocols

    BPF = import_bcc()

    # Load BPF functions (SCHED_ACT mode like sqredirect)
    fn_incoming = bpf.load_func("incoming", BPF.SCHED_ACT)
    fn_outgoing = bpf.load_func("outgoing", BPF.SCHED_ACT)

    logger.info(f"Loaded BPF functions: incoming={fn_incoming.name}, outgoing={fn_outgoing.name}")

    # Get interface index
    links = ipr.link_lookup(ifname=interface)
    if not links:
        raise RuntimeError(f"Network interface '{interface}' not found")
    ifindex = links[0]
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
        rollback_tc_bpf(ipr, ifindex, ingress_added, ingress_filter_added, sfq_added)
        raise RuntimeError("Failed to attach tc bpf, partial state rolled back") from e


def cleanup_tc(ipr: Any, ifindex: int, safe: bool = False) -> None:
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
        # Ignore 'Invalid argument' if safe mode (qdisc doesn't exist)
        is_not_found = exc.args[1] == 'Invalid argument'
        if safe and is_not_found:
            return
        logger.error(f"Failed to remove ingress qdisc: {exc}")
        if not safe:
            raise

    try:
        ipr.tc("del", "sfq", ifindex, "1:")
        logger.debug("Removed sfq qdisc")
    except NetlinkError as exc:
        # Ignore 'Invalid argument' if safe mode (qdisc doesn't exist)
        is_not_found = exc.args[1] == 'Invalid argument'
        if safe and is_not_found:
            return
        logger.error(f"Failed to remove sfq qdisc: {exc}")
        if not safe:
            raise
