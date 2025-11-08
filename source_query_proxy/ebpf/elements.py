"""
BPF Code Elements

Base classes for building BPF C code components.
"""

from typing import List, Tuple, Optional


class BPFElement:
    """Base class for all BPF code elements"""

    def render(self) -> str:
        """Generate C code for this element"""
        raise NotImplementedError(f"{self.__class__.__name__} must implement render()")


class BPFStruct(BPFElement):
    """C struct definition

    Example:
        struct addr_key_t {
            u32 ip;
            u16 port;
        };
    """

    def __init__(self, name: str, fields: List[Tuple[str, str]]):
        """
        Args:
            name: Struct name (e.g., "addr_key_t")
            fields: List of (type, name) tuples
                   e.g., [("u32", "ip"), ("u16", "port")]
        """
        self.name = name
        self.fields = fields

    def render(self) -> str:
        """Generate C struct definition"""
        lines = [f"struct {self.name} {{"]
        for field_type, field_name in self.fields:
            lines.append(f"    {field_type} {field_name};")
        lines.append("};")
        return "\n".join(lines)


class BPFMap(BPFElement):
    """BPF hash map definition

    Supports BPF_HASH, BPF_ARRAY, and other map types.

    Example:
        BPF_HASH(port_map, u16, u16, 1024);
    """

    def __init__(
        self,
        name: str,
        key_type: str,
        value_type: str,
        max_entries: int = 10240,
        map_type: str = "BPF_HASH"
    ):
        """
        Args:
            name: Map variable name
            key_type: C type for keys (e.g., "u16", "struct addr_key_t")
            value_type: C type for values (e.g., "u16", "u32")
            max_entries: Maximum number of entries in map
            map_type: BPF map type (BPF_HASH, BPF_ARRAY, etc.)
        """
        self.name = name
        self.key_type = key_type
        self.value_type = value_type
        self.max_entries = max_entries
        self.map_type = map_type

    def render(self) -> str:
        """Generate BPF map definition"""
        return f"{self.map_type}({self.name}, {self.key_type}, {self.value_type}, {self.max_entries});"


class BPFFunction(BPFElement):
    """BPF program function

    Example:
        int incoming(struct __sk_buff *skb) {
            // function body
            return TC_ACT_OK;
        }
    """

    def __init__(
        self,
        name: str,
        return_type: str = "int",
        params: Optional[List[Tuple[str, str]]] = None
    ):
        """
        Args:
            name: Function name
            return_type: Return type (default: "int")
            params: List of (type, name) tuples for parameters
                   Default: [("struct __sk_buff", "*skb")]
        """
        self.name = name
        self.return_type = return_type
        self.params = params or [("struct __sk_buff", "*skb")]
        self.body_parts: List[str] = []

    def add_code(self, code: str):
        """Add code block to function body

        Args:
            code: C code to add (will be indented automatically)
        """
        self.body_parts.append(code)

    def render(self) -> str:
        """Generate complete function with signature and body"""
        # Build parameter list
        param_strs = []
        for param_type, param_name in self.params:
            param_strs.append(f"{param_type} {param_name}")
        params_str = ", ".join(param_strs)

        # Build function signature
        signature = f"{self.return_type} {self.name}({params_str})"

        # Build function body
        lines = [signature + " {"]
        for code_block in self.body_parts:
            # Add code block (already should be indented)
            lines.append(code_block)
        lines.append("}")

        return "\n".join(lines)
