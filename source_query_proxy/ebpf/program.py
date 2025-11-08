"""
BPF Program Orchestrator

Manages the complete BPF program and generates final C code.
"""

from typing import List, TYPE_CHECKING

from .elements import BPFElement, BPFStruct, BPFMap, BPFFunction

if TYPE_CHECKING:
    from .operations import BPFOperation


class BPFProgram:
    """Complete BPF program that can be compiled and loaded

    Orchestrates all BPF elements (structs, maps, functions) and
    generates complete C code ready for BCC compilation.

    Example:
        program = BPFProgram("redirect")
        program.add_struct(BPFStruct("addr_key_t", [("u32", "ip"), ("u16", "port")]))
        program.add_map(BPFMap("port_map", "u16", "u16"))
        program.add_function(some_function)
        c_code = program.render()
    """

    def __init__(self, name: str):
        """
        Args:
            name: Program name (for documentation/debugging)
        """
        self.name = name
        self.includes: List[str] = [
            "<uapi/linux/bpf.h>",
            "<uapi/linux/if_ether.h>",
            "<uapi/linux/ip.h>",
            "<uapi/linux/udp.h>",
            "<uapi/linux/pkt_cls.h>",
        ]
        self.structs: List[BPFStruct] = []
        self.maps: List[BPFMap] = []
        self.functions: List[BPFFunction] = []

    def add_include(self, include: str):
        """Add an include directive

        Args:
            include: Include path (e.g., "<linux/types.h>")
        """
        if include not in self.includes:
            self.includes.append(include)

    def add_struct(self, struct: BPFStruct):
        """Add a struct definition

        Args:
            struct: BPFStruct instance
        """
        self.structs.append(struct)

    def add_map(self, map: BPFMap):
        """Add a BPF map

        Args:
            map: BPFMap instance
        """
        self.maps.append(map)

    def add_function(self, func: BPFFunction):
        """Add a BPF function

        Args:
            func: BPFFunction instance
        """
        self.functions.append(func)

    def apply_operation(self, operation: 'BPFOperation'):
        """Apply a high-level operation to this program

        Operations can add multiple elements (structs, maps, functions)
        in a composable way.

        Args:
            operation: BPFOperation instance to apply
        """
        operation.apply(self)

    def render(self) -> str:
        """Generate complete BPF C code

        Returns:
            Complete C code ready for BCC compilation
        """
        parts = []

        # Includes
        for inc in self.includes:
            parts.append(f"#include {inc}")
        parts.append("")

        # Structs
        if self.structs:
            for struct in self.structs:
                parts.append(struct.render())
                parts.append("")

        # Maps
        if self.maps:
            for map in self.maps:
                parts.append(map.render())
            parts.append("")

        # Functions
        for func in self.functions:
            parts.append(func.render())
            parts.append("")

        return "\n".join(parts)
