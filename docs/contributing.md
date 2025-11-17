# Contributing to sqproxy

Thank you for your interest in contributing to Source Query Proxy!

## Code of Conduct

Be respectful and constructive. We welcome contributions from everyone.

## How to Contribute

### Reporting Bugs

1. **Check existing issues** - Search [GitHub Issues](https://github.com/sqproxy/sqproxy/issues)
2. **Create detailed report** - Include:
   - sqproxy version (`sqproxy --version`)
   - Python version (`python3 --version`)
   - Operating system and kernel version
   - Configuration (remove sensitive data)
   - Full error message and stack trace
   - Steps to reproduce

### Suggesting Features

1. **Check existing issues** - Feature may already be planned
2. **Create feature request** - Include:
   - Use case - What problem does it solve?
   - Proposed solution
   - Alternatives considered
   - Implementation complexity estimate

### Contributing Code

#### 1. Fork and Clone

```bash
# Fork on GitHub
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/sqproxy.git
cd sqproxy

# Add upstream remote
git remote add upstream https://github.com/sqproxy/sqproxy.git
```

#### 2. Create Branch

```bash
# Update main
git checkout main
git pull upstream main

# Create feature branch
git checkout -b feature/my-feature
```

Use descriptive branch names:
- `feature/add-ipv6-support`
- `fix/memory-leak-in-cache`
- `docs/improve-configuration-guide`

#### 3. Setup Development Environment

```bash
# Install dependencies
poetry install

# Or with pip
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

#### 4. Make Changes

Follow these guidelines:

**Code Style**:
- Use [Black](https://black.readthedocs.io/) for formatting
- Follow [PEP 8](https://pep8.org/)
- Use type hints
- Maximum line length: 100 characters

**Documentation**:
- Document all public APIs
- Update relevant documentation in `docs/`
- Add docstrings to functions/classes

**Tests**:
- Add tests for new features
- Maintain or improve code coverage
- All tests must pass

#### 5. Commit Changes

Use [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git commit -m "feat: add IPv6 support for eBPF redirection"
git commit -m "fix: resolve memory leak in A2S cache"
git commit -m "docs: update configuration guide"
git commit -m "test: add tests for PacketRedirectOperation"
```

**Commit types**:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `style:` - Code style (formatting, semicolons, etc.)
- `refactor:` - Code refactoring
- `perf:` - Performance improvement
- `test:` - Adding/updating tests
- `chore:` - Build process, dependencies, etc.
- `ci:` - CI/CD changes

#### 6. Push and Create PR

```bash
# Push to your fork
git push origin feature/my-feature
```

Create Pull Request on GitHub:

1. Click "New Pull Request"
2. Select your branch
3. Fill in PR template:
   - Description of changes
   - Related issues
   - Testing done
   - Breaking changes (if any)

#### 7. Code Review

Maintainers will review your PR. Be prepared to:
- Answer questions
- Make requested changes
- Discuss implementation details

## Development Workflow

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=source_query_proxy --cov-report=html

# Specific test
pytest tests/test_ebpf_generation.py::test_struct

# Watch mode
pytest-watch
```

### Code Quality

```bash
# Format code
black source_query_proxy/ tests/

# Check formatting
black --check source_query_proxy/ tests/

# Lint
flake8 source_query_proxy/ tests/

# Type checking
mypy source_query_proxy/

# All checks
pre-commit run --all-files
```

### Building Documentation

```bash
# Install mkdocs
pip install mkdocs-material

# Serve locally
mkdocs serve

# Build
mkdocs build
```

### Manual Testing

```bash
# Run locally
python3 -m source_query_proxy run

# With debug logging
SQPROXY_LOGLEVEL=DEBUG python3 -m source_query_proxy run
```

## Contributing to eBPF

### Template Engine

Located in `source_query_proxy/ebpf/`:

**Adding new BPF element**:

```python
# source_query_proxy/ebpf/elements.py
class BPFNewElement(BPFElement):
    def __init__(self, name: str):
        self.name = name

    def render(self) -> str:
        return f"// {self.name}"
```

**Adding new operation**:

```python
# source_query_proxy/ebpf/operations.py
class NewOperation(BPFOperation):
    def apply_to_program(self, program: BPFProgram):
        # Add elements to program
        program.add_element(BPFNewElement("test"))
```

**Add tests**:

```python
# tests/test_ebpf_generation.py
def test_new_element():
    element = BPFNewElement("test")
    assert element.render() == "// test"

def test_new_operation():
    program = BPFProgram("test")
    operation = NewOperation()
    operation.apply_to_program(program)

    code = program.render()
    assert "// test" in code
```

## Documentation Contributions

### Adding New Page

1. Create markdown file in `docs/`:
```bash
touch docs/my-new-page.md
```

2. Add to `mkdocs.yml`:
```yaml
nav:
  - My Section:
    - My New Page: my-new-page.md
```

3. Write content using markdown

### Documentation Style

- Use clear, concise language
- Include code examples
- Add command-line examples with expected output
- Use admonitions for important notes:

```markdown
!!! note "Important"
    This is important information

!!! warning "Warning"
    This is a warning

!!! tip "Tip"
    This is a helpful tip
```

## Review Process

### What We Look For

1. **Functionality** - Does it work as intended?
2. **Tests** - Are there tests? Do they pass?
3. **Code Quality** - Is code clean and maintainable?
4. **Documentation** - Is it documented?
5. **Breaking Changes** - Are they necessary and documented?

### Timeline

- Initial review: 1-3 days
- Follow-up: 1-2 days
- Merge: After approval from 1+ maintainers

## Release Process

Maintainers handle releases:

1. Update version in `pyproject.toml` and `setup.py`
2. Update `CHANGELOG.md`
3. Create git tag: `v3.1.0`
4. Build and publish to PyPI
5. Create GitHub release

## Getting Help

- **Questions**: [GitHub Discussions](https://github.com/sqproxy/sqproxy/discussions)
- **Chat**: (TBD)
- **Email**: (TBD)

## Recognition

Contributors are recognized in:
- GitHub contributors page
- Release notes
- `CONTRIBUTORS.md` (for significant contributions)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Thank You!

Every contribution helps make sqproxy better. Thank you for contributing!
