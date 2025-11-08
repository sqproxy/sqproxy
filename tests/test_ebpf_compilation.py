"""
Integration tests for eBPF code compilation with BCC

These tests verify that generated BPF C code can be compiled by BCC.
Note: These tests require BCC to be installed (python3-bpfcc package).
"""

import pytest

from source_query_proxy.ebpf import BPFProgram, PacketRedirectOperation

# Check if BCC is available
try:
    from bcc import BPF

    BCC_AVAILABLE = True
except ImportError:
    BCC_AVAILABLE = False


@pytest.mark.skipif(not BCC_AVAILABLE, reason="BCC not installed")
class TestBPFCompilation:
    """Test BPF code compilation with BCC"""

    def test_port_only_redirect_compiles(self):
        """Test that port-only redirect code compiles with BCC"""
        # Generate BPF program
        program = BPFProgram("test_port_redirect")
        op = PacketRedirectOperation(
            server_port=27015, bind_port=27016, use_ipport_key=False
        )
        program.apply_operation(op)
        bpf_code = program.render()

        # Verify code is not empty
        assert len(bpf_code) > 100
        assert "int incoming" in bpf_code
        assert "int outgoing" in bpf_code

        # Try to compile with BCC
        try:
            b = BPF(text=bpf_code, debug=0)

            # Verify functions are loadable (but don't actually load them)
            # This checks that the BPF bytecode is valid
            assert hasattr(b, "load_func")

            # Check that our functions exist in the compiled program
            incoming_fn = b.load_func("incoming", BPF.SCHED_CLS)
            outgoing_fn = b.load_func("outgoing", BPF.SCHED_CLS)

            assert incoming_fn is not None
            assert outgoing_fn is not None

            # Check that maps are created
            port_map = b.get_table("port_map")
            assert port_map is not None

        except Exception as e:
            pytest.fail(f"BPF compilation failed: {e}\n\nGenerated code:\n{bpf_code}")

    def test_ipport_redirect_compiles(self):
        """Test that IP+port redirect code compiles with BCC"""
        # Generate BPF program
        program = BPFProgram("test_ipport_redirect")
        op = PacketRedirectOperation(
            server_port=27015,
            bind_port=27016,
            bind_ip="192.168.1.1",
            use_ipport_key=True,
        )
        program.apply_operation(op)
        bpf_code = program.render()

        # Verify code is not empty
        assert len(bpf_code) > 100
        assert "struct addr_key_t" in bpf_code
        assert "int incoming" in bpf_code
        assert "int outgoing" in bpf_code

        # Try to compile with BCC
        try:
            b = BPF(text=bpf_code, debug=0)

            # Verify functions are loadable
            incoming_fn = b.load_func("incoming", BPF.SCHED_CLS)
            outgoing_fn = b.load_func("outgoing", BPF.SCHED_CLS)

            assert incoming_fn is not None
            assert outgoing_fn is not None

            # Check that addr_map is created
            addr_map = b.get_table("addr_map")
            assert addr_map is not None

        except Exception as e:
            pytest.fail(f"BPF compilation failed: {e}\n\nGenerated code:\n{bpf_code}")

    def test_generated_code_syntax(self):
        """Test that generated code has valid C syntax"""
        program = BPFProgram("test_syntax")
        op = PacketRedirectOperation(server_port=27015, bind_port=27016)
        program.apply_operation(op)
        bpf_code = program.render()

        # Basic syntax checks
        assert bpf_code.count("{") == bpf_code.count("}")  # Balanced braces
        assert bpf_code.count("(") == bpf_code.count(")")  # Balanced parens

        # Check for required BPF includes
        assert "#include <uapi/linux/bpf.h>" in bpf_code
        assert "#include <uapi/linux/if_ether.h>" in bpf_code
        assert "#include <uapi/linux/ip.h>" in bpf_code
        assert "#include <uapi/linux/udp.h>" in bpf_code

        # Try to compile (final verification)
        try:
            BPF(text=bpf_code, debug=0)
        except Exception as e:
            pytest.fail(f"Syntax validation failed: {e}")

    def test_multiple_ports_same_program(self):
        """Test that we can create a program handling multiple port mappings"""
        # This tests the approach we'll use in epbf.py
        program = BPFProgram("multi_port")

        # For now, just test that one operation works
        # In the future, we need to support multiple mappings in one program
        op = PacketRedirectOperation(server_port=27015, bind_port=27016)
        program.apply_operation(op)

        bpf_code = program.render()

        try:
            b = BPF(text=bpf_code, debug=0)

            # Test that we can populate the map with multiple entries
            port_map = b.get_table("port_map")

            # Add multiple port mappings
            port_map[27015] = 27016
            port_map[27016] = 27017
            port_map[27017] = 27018

            # Verify mappings
            assert port_map[27015].value == 27016
            assert port_map[27016].value == 27017
            assert port_map[27017].value == 27018

        except Exception as e:
            pytest.fail(f"Multi-port test failed: {e}")

    @pytest.mark.parametrize(
        "server_port,bind_port",
        [
            (27015, 27816),
            (27016, 27817),
            (7777, 7778),
            (25565, 25566),  # Minecraft
        ],
    )
    def test_various_port_combinations(self, server_port, bind_port):
        """Test compilation with various port numbers"""
        program = BPFProgram(f"test_{server_port}")
        op = PacketRedirectOperation(server_port=server_port, bind_port=bind_port)
        program.apply_operation(op)
        bpf_code = program.render()

        try:
            b = BPF(text=bpf_code, debug=0)
            port_map = b.get_table("port_map")
            port_map[server_port] = bind_port
            assert port_map[server_port].value == bind_port
        except Exception as e:
            pytest.fail(
                f"Compilation failed for ports {server_port}->{bind_port}: {e}"
            )


@pytest.mark.skipif(BCC_AVAILABLE, reason="Testing BCC unavailability handling")
def test_graceful_handling_without_bcc():
    """Test that code generation works even without BCC installed"""
    # This should always work - code generation doesn't require BCC
    program = BPFProgram("test_no_bcc")
    op = PacketRedirectOperation(server_port=27015, bind_port=27016)
    program.apply_operation(op)
    bpf_code = program.render()

    assert len(bpf_code) > 100
    assert "int incoming" in bpf_code
    assert "int outgoing" in bpf_code


def test_bcc_availability_reporting():
    """Report whether BCC is available for testing"""
    if BCC_AVAILABLE:
        from bcc import BPF

        print(f"\n✓ BCC is available: {BPF.__file__}")
    else:
        print("\n✗ BCC is NOT available - compilation tests will be skipped")
        print("  Install with: apt-get install python3-bpfcc")
