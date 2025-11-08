"""
eBPF Template Engine and Runtime for sqproxy

This package provides a complete solution for eBPF-based packet redirection:

Template Engine Components:
- elements: Base classes for BPF code elements (BPFStruct, BPFMap, BPFFunction)
- program: BPFProgram orchestrator that generates complete BPF C code
- operations: High-level composable operations (PacketRedirectOperation, etc.)

Runtime Components:
- runtime: Network helpers, BPF generation, and map population
- tc: Traffic control (tc) operations for attaching BPF programs
- redirector: EBPFRedirector lifecycle manager for async applications

Usage (Template Engine):
    from source_query_proxy.ebpf import BPFProgram, PacketRedirectOperation

    program = BPFProgram("redirect")
    program.apply_operation(PacketRedirectOperation(
        server_port=27015,
        bind_port=27016,
        bind_ip="192.168.1.1"
    ))
    bpf_c_code = program.render()

Usage (Runtime):
    from source_query_proxy.ebpf.redirector import EBPFRedirector

    async with EBPFRedirector() as redirector:
        # eBPF is active
        await asyncio.Event().wait()
"""

from .elements import BPFElement, BPFStruct, BPFMap, BPFFunction
from .program import BPFProgram
from .operations import BPFOperation, PacketRedirectOperation

__all__ = [
    # Template engine
    'BPFElement',
    'BPFStruct',
    'BPFMap',
    'BPFFunction',
    'BPFProgram',
    'BPFOperation',
    'PacketRedirectOperation',
    # Runtime components available via submodules:
    # - ebpf.runtime: Helpers and utilities
    # - ebpf.tc: Traffic control operations
    # - ebpf.redirector: EBPFRedirector class
]
