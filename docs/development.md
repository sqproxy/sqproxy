# Development Guide

Contributing to Source Query Proxy development.

## Setup Development Environment

### Clone Repository

```bash
git clone https://github.com/sqproxy/sqproxy.git
cd sqproxy
```

### Install with Poetry

```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Activate virtual environment
poetry shell
```

### Install with pip

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in editable mode
pip install -e .

# Install development dependencies
pip install -e ".[dev]"
```

## Project Structure

```
sqproxy/
├── source_query_proxy/          # Main package
│   ├── __init__.py
│   ├── __main__.py             # CLI entry point
│   ├── config.py               # Configuration loading
│   ├── epbf.py                 # eBPF main module
│   ├── proxy.py                # Proxy logic
│   ├── protocol/               # A2S protocol
│   └── ebpf/                   # eBPF implementation
│       ├── __init__.py
│       ├── elements.py         # BPF building blocks
│       ├── operations.py       # High-level operations
│       ├── program.py          # Program orchestrator
│       ├── redirector.py       # Lifecycle manager
│       ├── tc.py              # Traffic control
│       └── runtime.py         # Runtime utilities
├── tests/                      # Test suite
│   ├── test_ebpf_generation.py
│   ├── test_ebpf_compilation.py
│   └── docker/                 # Docker tests
├── examples/                   # Example configs
├── docs/                       # Documentation
├── pyproject.toml             # Poetry config
├── setup.py                   # setuptools config
└── README.rst
```

## Running Tests

### Unit Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=source_query_proxy

# Run specific test file
pytest tests/test_ebpf_generation.py

# Run specific test
pytest tests/test_ebpf_generation.py::TestBPFStruct::test_simple_struct
```

### Integration Tests (BCC)

```bash
# Requires BCC installed
pytest tests/test_ebpf_compilation.py

# Skip if BCC not available
pytest tests/test_ebpf_compilation.py --skip-bcc
```

### Docker Tests

```bash
cd tests/docker
docker-compose -f docker-compose.bpf-test.yml up --build
```

## Code Style

### Formatting

```bash
# Format code with black
black source_query_proxy/ tests/

# Check formatting
black --check source_query_proxy/ tests/
```

### Linting

```bash
# Run flake8
flake8 source_query_proxy/ tests/

# Run mypy (type checking)
mypy source_query_proxy/
```

### Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Setup hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Making Changes

### 1. Create Branch

```bash
git checkout -b feature/my-feature
```

### 2. Make Changes

Edit code following style guidelines.

### 3. Add Tests

```python
# tests/test_my_feature.py
def test_my_feature():
    result = my_function()
    assert result == expected
```

### 4. Run Tests

```bash
pytest
black --check .
flake8
```

### 5. Commit

```bash
git add .
git commit -m "feat: add my feature

Detailed description of changes"
```

Use conventional commits:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `test:` - Tests
- `refactor:` - Code refactoring
- `ci:` - CI/CD changes

### 6. Push and Create PR

```bash
git push origin feature/my-feature
```

Create pull request on GitHub.

## eBPF Development

### Template Engine

Modify BPF code generation in `source_query_proxy/ebpf/`:

```python
# elements.py - Add new BPF element
class BPFCustomElement(BPFElement):
    def render(self) -> str:
        return "// Custom BPF code"

# operations.py - Add new operation
class CustomOperation(BPFOperation):
    def apply_to_program(self, program: BPFProgram):
        program.add_element(BPFCustomElement())
```

### Testing BPF Generation

```python
# tests/test_ebpf_generation.py
def test_custom_operation():
    program = BPFProgram("test")
    operation = CustomOperation()
    operation.apply_to_program(program)

    code = program.render()
    assert "Custom BPF code" in code
```

### Testing BPF Compilation

```python
# tests/test_ebpf_compilation.py
def test_custom_bpf_compiles():
    program = BPFProgram("test")
    operation = CustomOperation()
    operation.apply_to_program(program)

    code = program.render()
    bpf = BPF(text=code)  # Should compile
```

## Documentation

### Build Documentation

```bash
# Install mkdocs
pip install mkdocs-material

# Serve locally
mkdocs serve

# Open http://127.0.0.1:8000

# Build static site
mkdocs build
```

### Add New Page

1. Create markdown file in `docs/`
2. Add to `mkdocs.yml`:

```yaml
nav:
  - Home: index.md
  - My New Page: my-page.md
```

## Debugging

### Debug eBPF

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Print generated BPF code
from source_query_proxy.ebpf import BPFProgram, PacketRedirectOperation

program = BPFProgram("debug")
operation = PacketRedirectOperation(server_port=27015, bind_port=27016)
operation.apply_to_program(program)

print(program.render())
```

### Debug with pdb

```python
# Add breakpoint
import pdb; pdb.set_trace()

# Or use breakpoint() in Python 3.7+
breakpoint()
```

### Profile Performance

```bash
# CPU profiling
python3 -m cProfile -o profile.stats sqproxy run

# Analyze
python3 -m pstats profile.stats

# Memory profiling
python3 -m memory_profiler sqproxy run
```

## Release Process

### 1. Update Version

Edit `pyproject.toml` and `setup.py`:

```toml
[tool.poetry]
version = "3.1.0"
```

### 2. Update CHANGELOG

Add entry to `CHANGELOG.md`:

```markdown
## v3.1.0 (2024-01-15)

### Feat
- New feature description

### Fix
- Bug fix description
```

### 3. Commit and Tag

```bash
git add .
git commit -m "chore: bump version to 3.1.0"
git tag v3.1.0
git push origin main --tags
```

### 4. Build and Publish

```bash
# Build package
poetry build

# Publish to PyPI
poetry publish

# Or with twine
python3 setup.py sdist bdist_wheel
twine upload dist/*
```

## CI/CD

### GitHub Actions

Workflows in `.github/workflows/`:

- `tests.yml` - Run tests on push/PR
- `ebpf-tests.yml` - Run eBPF compilation tests
- `release.yml` - Publish to PyPI on tag

### Local CI Testing

```bash
# Install act
brew install act  # macOS
# or download from https://github.com/nektos/act

# Run GitHub Actions locally
act -j test
```

## Best Practices

### 1. Write Tests First

```python
# Write test
def test_new_feature():
    assert new_feature() == expected

# Then implement
def new_feature():
    return expected
```

### 2. Document Public APIs

```python
def my_function(arg: str) -> int:
    """Short description.

    Longer description explaining what the function does.

    Args:
        arg: Description of argument

    Returns:
        Description of return value

    Raises:
        ValueError: When arg is invalid
    """
    pass
```

### 3. Use Type Hints

```python
from typing import List, Optional

def process_servers(servers: List[dict]) -> Optional[str]:
    pass
```

### 4. Keep Functions Small

- One function = one responsibility
- Max ~50 lines per function
- Extract helpers when needed

### 5. Error Handling

```python
try:
    risky_operation()
except SpecificError as e:
    logger.error(f"Operation failed: {e}")
    raise RuntimeError("Helpful message") from e
```

## Resources

- [Python Style Guide (PEP 8)](https://pep8.org/)
- [Type Hints (PEP 484)](https://www.python.org/dev/peps/pep-0484/)
- [BCC Documentation](https://github.com/iovisor/bcc)
- [eBPF Documentation](https://ebpf.io/)
- [pytest Documentation](https://docs.pytest.org/)

## Getting Help

- **GitHub Issues**: https://github.com/sqproxy/sqproxy/issues
- **GitHub Discussions**: https://github.com/sqproxy/sqproxy/discussions
- **Documentation**: https://sqproxy.readthedocs.io/
