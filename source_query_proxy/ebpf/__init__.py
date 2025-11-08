"""
eBPF Template Engine for sqproxy

This package provides a class-based template engine for generating eBPF C code.
It replaces the external sqredirect dependency with internal code generation.

Main components:
- elements: Base classes for BPF code elements (BPFStruct, BPFMap, BPFFunction)
- program: BPFProgram orchestrator that generates complete BPF C code
- operations: High-level composable operations (PacketRedirectOperation, etc.)

Usage:
    from source_query_proxy.ebpf import BPFProgram, PacketRedirectOperation

    program = BPFProgram("redirect")
    program.apply_operation(PacketRedirectOperation(
        server_port=27015,
        bind_port=27016,
        bind_ip="192.168.1.1"
    ))
    bpf_c_code = program.render()
"""

from .elements import BPFElement, BPFStruct, BPFMap, BPFFunction
from .program import BPFProgram
from .operations import BPFOperation, PacketRedirectOperation

__all__ = [
    'BPFElement',
    'BPFStruct',
    'BPFMap',
    'BPFFunction',
    'BPFProgram',
    'BPFOperation',
    'PacketRedirectOperation',
]
