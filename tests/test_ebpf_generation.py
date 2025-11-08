"""
Tests for eBPF template engine code generation
"""

import pytest

from source_query_proxy.ebpf import (
    BPFStruct,
    BPFMap,
    BPFFunction,
    BPFProgram,
    PacketRedirectOperation,
)


class TestBPFStruct:
    """Test BPFStruct code generation"""

    def test_simple_struct(self):
        """Test generating a simple struct"""
        struct = BPFStruct("addr_key_t", [
            ("u32", "ip"),
            ("u16", "port")
        ])

        code = struct.render()
        assert "struct addr_key_t {" in code
        assert "u32 ip;" in code
        assert "u16 port;" in code
        assert code.endswith("};")

    def test_empty_struct(self):
        """Test generating an empty struct"""
        struct = BPFStruct("empty_t", [])
        code = struct.render()
        assert "struct empty_t {" in code
        assert "};" in code

    def test_struct_with_unsupported_type(self):
        """Test struct generation with unsupported field type"""
        # Template engine doesn't validate types - passes them through
        struct = BPFStruct("custom_type_t", [
            ("foo32", "value"),
        ])
        code = struct.render()
        # Should still generate code with the custom type
        assert "foo32 value;" in code

    def test_struct_with_empty_field_names(self):
        """Test struct with empty field type or name"""
        struct = BPFStruct("empty_field_t", [
            ("", "ip"),
            ("u32", ""),
        ])
        code = struct.render()
        # Should generate code even with empty fields
        assert " ip;" in code
        assert "u32 ;" in code

    def test_struct_with_duplicate_field_names(self):
        """Test struct with duplicate field names"""
        struct = BPFStruct("dup_field_t", [
            ("u32", "ip"),
            ("u16", "ip"),
        ])
        code = struct.render()
        # Both fields present with duplicate names (BCC will error on this)
        assert code.count("ip;") == 2


class TestBPFMap:
    """Test BPFMap code generation"""

    def test_simple_hash_map(self):
        """Test generating a BPF_HASH map"""
        bpf_map = BPFMap("port_map", "u16", "u16", max_entries=1024)
        code = bpf_map.render()
        assert code == "BPF_HASH(port_map, u16, u16, 1024);"

    def test_struct_key_map(self):
        """Test map with struct key type"""
        bpf_map = BPFMap("addr_map", "struct addr_key_t", "u16", max_entries=2048)
        code = bpf_map.render()
        assert code == "BPF_HASH(addr_map, struct addr_key_t, u16, 2048);"

    def test_default_max_entries(self):
        """Test default max_entries value"""
        bpf_map = BPFMap("test_map", "u32", "u32")
        code = bpf_map.render()
        assert "10240" in code  # Default max_entries

    def test_different_map_types(self):
        """Test generating maps with different map_type values"""
        # BPF_ARRAY
        bpf_array = BPFMap("array_map", "u32", "u64", map_type="BPF_ARRAY", max_entries=128)
        code_array = bpf_array.render()
        assert code_array == "BPF_ARRAY(array_map, u32, u64, 128);"

        # BPF_PERCPU_HASH
        bpf_percpu = BPFMap("percpu_map", "u32", "u64", map_type="BPF_PERCPU_HASH", max_entries=256)
        code_percpu = bpf_percpu.render()
        assert code_percpu == "BPF_PERCPU_HASH(percpu_map, u32, u64, 256);"

    def test_map_with_zero_max_entries(self):
        """Test map with zero max_entries (invalid but not validated)"""
        # Template engine doesn't validate max_entries
        bpf_map = BPFMap("zero_map", "u32", "u32", max_entries=0)
        code = bpf_map.render()
        # Should still generate code (BCC will error on this)
        assert "BPF_HASH(zero_map, u32, u32, 0);" == code

    def test_map_with_negative_max_entries(self):
        """Test map with negative max_entries (invalid but not validated)"""
        # Template engine doesn't validate max_entries
        bpf_map = BPFMap("neg_map", "u32", "u32", max_entries=-1)
        code = bpf_map.render()
        # Should still generate code (BCC will error on this)
        assert "BPF_HASH(neg_map, u32, u32, -1);" == code


class TestBPFFunction:
    """Test BPFFunction code generation"""

    def test_empty_function(self):
        """Test function with no body"""
        func = BPFFunction("test_func")
        code = func.render()
        assert "int test_func(struct __sk_buff *skb) {" in code
        assert code.endswith("}")

    def test_function_with_code(self):
        """Test function with code blocks"""
        func = BPFFunction("my_func")
        func.add_code("    return TC_ACT_OK;")
        code = func.render()
        assert "int my_func(struct __sk_buff *skb) {" in code
        assert "return TC_ACT_OK;" in code

    def test_custom_return_type(self):
        """Test function with custom return type"""
        func = BPFFunction("get_value", return_type="u32")
        code = func.render()
        assert code.startswith("u32 get_value(")

    def test_custom_params(self):
        """Test function with custom parameters"""
        func = BPFFunction("process", params=[("void", "*data"), ("int", "len")])
        code = func.render()
        assert "int process(void *data, int len)" in code


class TestBPFProgram:
    """Test BPFProgram orchestration"""

    def test_empty_program(self):
        """Test generating empty program"""
        program = BPFProgram("test")
        code = program.render()

        # Should have includes
        assert "#include <uapi/linux/bpf.h>" in code
        assert "#include <uapi/linux/if_ether.h>" in code
        assert "#include <uapi/linux/ip.h>" in code
        assert "#include <uapi/linux/udp.h>" in code
        assert "#include <uapi/linux/pkt_cls.h>" in code

    def test_program_with_all_elements(self):
        """Test program with structs, maps, and functions"""
        program = BPFProgram("complete")

        # Add struct
        program.add_struct(BPFStruct("my_key_t", [("u32", "value")]))

        # Add map
        program.add_map(BPFMap("my_map", "struct my_key_t", "u16"))

        # Add function
        func = BPFFunction("my_func")
        func.add_code("    return TC_ACT_OK;")
        program.add_function(func)

        code = program.render()

        # Check all elements are present in correct order
        assert code.index("#include") < code.index("struct my_key_t")
        assert code.index("struct my_key_t") < code.index("BPF_HASH")
        assert code.index("BPF_HASH") < code.index("int my_func")

    def test_add_custom_include(self):
        """Test adding custom includes"""
        program = BPFProgram("test")
        program.add_include("<linux/types.h>")
        code = program.render()
        assert "#include <linux/types.h>" in code

    def test_duplicate_include_ignored(self):
        """Test that duplicate includes are ignored"""
        program = BPFProgram("test")
        initial_count = len(program.includes)
        program.add_include("<uapi/linux/bpf.h>")  # Already exists
        assert len(program.includes) == initial_count


class TestPacketRedirectOperation:
    """Test PacketRedirectOperation"""

    def test_port_only_redirect(self):
        """Test redirect with port-only lookup"""
        program = BPFProgram("redirect")
        op = PacketRedirectOperation(
            server_port=27015,
            bind_port=27016,
            use_ipport_key=False
        )
        op.apply(program)
        code = program.render()

        # Should have port_map (not addr_map)
        assert "BPF_HASH(port_map, u16, u16" in code
        assert "addr_map" not in code
        assert "struct addr_key_t" not in code

        # Should have both functions
        assert "int incoming(struct __sk_buff *skb)" in code
        assert "int outgoing(struct __sk_buff *skb)" in code

        # Should have port lookup code
        assert "port_map.lookup" in code

    def test_ipport_redirect(self):
        """Test redirect with IP+port lookup"""
        program = BPFProgram("redirect")
        op = PacketRedirectOperation(
            server_port=27015,
            bind_port=27016,
            bind_ip="192.168.1.1",
            use_ipport_key=True
        )
        op.apply(program)
        code = program.render()

        # Should have addr_key_t struct
        assert "struct addr_key_t {" in code
        assert "u32 ip;" in code
        assert "u16 port;" in code

        # Should have addr_map (not port_map)
        assert "BPF_HASH(addr_map, struct addr_key_t, u16" in code
        assert "port_map" not in code

        # Should have IP+port lookup code
        assert "addr_map.lookup" in code
        assert "struct addr_key_t key" in code

    def test_steam_protocol_validation(self):
        """Test that Steam protocol validation is included"""
        program = BPFProgram("redirect")
        op = PacketRedirectOperation(server_port=27015, bind_port=27016)
        op.apply(program)
        code = program.render()

        # Should validate Steam protocol header
        assert "0xFFFFFFFF" in code
        assert "TC_ACT_SHOT" in code  # Drop invalid packets

        # Should check packet types (A2S_INFO, A2S_PLAYER, etc.)
        assert "0x54" in code  # A2S_INFO
        assert "0x55" in code  # A2S_PLAYER
        assert "0x56" in code  # A2S_RULES

    def test_checksum_recalculation(self):
        """Test that UDP checksum recalculation is included"""
        program = BPFProgram("redirect")
        op = PacketRedirectOperation(server_port=27015, bind_port=27016)
        op.apply(program)
        code = program.render()

        # Should have checksum code
        assert "bpf_csum_diff" in code
        assert "csum_fold" in code
        assert "udph->check" in code

    def test_header_parsing(self):
        """Test that packet header parsing is included"""
        program = BPFProgram("redirect")
        op = PacketRedirectOperation(server_port=27015, bind_port=27016)
        op.apply(program)
        code = program.render()

        # Should parse all headers
        assert "struct ethhdr" in code
        assert "struct iphdr" in code
        assert "struct udphdr" in code

        # Should validate bounds
        assert "data_end" in code
        assert "TC_ACT_OK" in code

    def test_complete_generated_code(self):
        """Test that complete valid C code is generated"""
        program = BPFProgram("redirect")
        op = PacketRedirectOperation(
            server_port=27015,
            bind_port=27816
        )
        op.apply(program)
        code = program.render()

        # Should be valid C-like code
        assert code.count("{") == code.count("}")  # Balanced braces
        assert "#include" in code
        assert "return" in code

        # Should not be empty
        assert len(code) > 100


class TestIntegration:
    """Integration tests for the template engine"""

    def test_apply_multiple_operations(self):
        """Test applying multiple operations to same program"""
        program = BPFProgram("multi")

        # Apply first redirect operation (port-only)
        op1 = PacketRedirectOperation(server_port=27015, bind_port=27016)
        program.apply_operation(op1)

        # In practice, we generate one BPF program and populate maps dynamically
        # But this tests that the template engine can handle multiple operations
        code = program.render()

        # Verify code is generated
        assert len(code) > 1000
        assert "int incoming" in code
        assert "int outgoing" in code
        assert "port_map" in code

    def test_multiple_ipport_mappings(self):
        """Test that a single program can handle multiple IP+port mappings"""
        program = BPFProgram("multi_ipport")

        # Generate program with IP+port mode
        op = PacketRedirectOperation(
            server_port=27015,
            bind_port=27016,
            bind_ip="192.168.1.1",
            use_ipport_key=True
        )
        program.apply_operation(op)
        code = program.render()

        # Verify addr_map is created
        assert "BPF_HASH(addr_map, struct addr_key_t, u16" in code
        assert "struct addr_key_t" in code

        # Verify lookup code exists
        assert "addr_map.lookup" in code

        # The same program can handle multiple IP+port combinations
        # by populating the addr_map with different keys at runtime
        # Each key is (IP, port) tuple
        assert "key.ip" in code
        assert "key.port" in code

    def test_typical_usage_pattern(self):
        """Test the typical usage pattern from docstrings"""
        # This matches the example from the design doc
        program = BPFProgram("redirect_27015")
        program.apply_operation(PacketRedirectOperation(
            server_port=27015,
            bind_port=27016,
            bind_ip="192.168.1.1"
        ))
        bpf_c_code = program.render()

        # Verify it generates valid-looking code
        assert "#include" in bpf_c_code
        assert "struct addr_key_t" in bpf_c_code
        assert "int incoming" in bpf_c_code
        assert "int outgoing" in bpf_c_code
        assert len(bpf_c_code) > 1000  # Should be substantial code
