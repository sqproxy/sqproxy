# eBPF Docker Test Environment

This directory contains Docker-based testing infrastructure for eBPF code generation and compilation.

## Overview

The eBPF template engine generates BPF C code that needs to be compiled with BCC (BPF Compiler Collection). These tests verify that:

1. **Code Generation**: Template engine produces valid BPF C code
2. **Compilation**: Generated code compiles successfully with BCC
3. **Map Operations**: BPF maps can be created and populated
4. **Function Loading**: BPF functions can be loaded (but not attached)

## Files

- `Dockerfile.bpf-test` - Container with BCC and test dependencies
- `docker-compose.bpf-test.yml` - Orchestrates test execution
- `README.md` - This file

## Running Tests Locally

### Using Docker Compose (Recommended)

```bash
cd tests/docker
docker-compose -f docker-compose.bpf-test.yml up --build
```

This will:
1. Build the test container with BCC installed
2. Run code generation tests
3. Run compilation tests with BCC
4. Exit with success/failure code

### Using Docker Directly

Build the image:
```bash
docker build -t sqproxy-bpf-test -f tests/docker/Dockerfile.bpf-test .
```

Run tests:
```bash
# Code generation tests
docker run --rm sqproxy-bpf-test python3 -m pytest tests/test_ebpf_generation.py -v

# BCC compilation tests
docker run --rm sqproxy-bpf-test python3 -m pytest tests/test_ebpf_compilation.py -v

# All eBPF tests
docker run --rm sqproxy-bpf-test python3 -m pytest tests/test_ebpf_*.py -v
```

## Test Categories

### Unit Tests (`test_ebpf_generation.py`)

Pure Python tests that verify template engine logic:
- ✅ No external dependencies (except pytest)
- ✅ Fast execution
- ✅ Test code structure and generation

**Run anywhere** - no BCC required.

### Integration Tests (`test_ebpf_compilation.py`)

Tests that compile generated BPF code with BCC:
- ⚠️ Requires BCC installation
- ⚠️ Slower (compilation overhead)
- ✅ Verifies real-world compilation

**Requires** Docker or BCC installed locally.

## GitHub Actions

The `.github/workflows/ebpf-tests.yml` workflow automatically:
1. Builds test container on every PR/push
2. Runs both test suites
3. Reports failures if compilation breaks

## Limitations

**What we CAN test**:
- ✅ BPF code generation
- ✅ BPF code compilation
- ✅ Map creation and population
- ✅ Function loading

**What we CANNOT test** (requires kernel access):
- ❌ Attaching BPF programs to network interfaces
- ❌ Actual packet redirection
- ❌ tc (traffic control) integration
- ❌ Real network traffic

For full integration testing with packet redirection, you need a VM or physical machine with:
- Linux kernel with eBPF support
- Root/sudo privileges
- Network interfaces to attach to

## Troubleshooting

### BCC Compilation Errors

If tests fail with compilation errors:
1. Check generated BPF C code (printed in test output)
2. Verify BCC version: `docker run --rm sqproxy-bpf-test dpkg -l | grep bpfcc`
3. Check for syntax errors in `source_query_proxy/ebpf/operations.py`

### Docker Build Fails

If Docker build fails:
1. Ensure you're running from project root
2. Check that `pyproject.toml` exists
3. Verify network connectivity (apt-get needs to download packages)

### Tests Skip with "BCC not installed"

This is expected when running unit tests without BCC. The tests will gracefully skip:
```
SKIPPED [1] tests/test_ebpf_compilation.py: BCC not installed
```

To run compilation tests, use Docker as shown above.

## Future Enhancements

Planned additions to test infrastructure:

1. **Full Integration Tests** (not yet implemented):
   - Simulated game server container
   - Actual packet redirection testing
   - tcpdump-based verification

2. **Performance Tests**:
   - Benchmark code generation speed
   - Measure compilation time

3. **Multi-Server Tests**:
   - Test handling multiple port mappings
   - Verify single BPF program approach

## Related Files

- `../../test_ebpf_generation.py` - Unit tests (no BCC required)
- `../../test_ebpf_compilation.py` - Integration tests (requires BCC)
- `../../../source_query_proxy/ebpf/` - Template engine source code
- `../../../.github/workflows/ebpf-tests.yml` - CI/CD configuration

## References

- [BCC GitHub](https://github.com/iovisor/bcc)
- [eBPF Documentation](https://ebpf.io/)
- [BCC Python API](https://github.com/iovisor/bcc/blob/master/docs/reference_guide.md)
