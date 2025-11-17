# sqproxy Documentation

This directory contains the complete documentation for Source Query Proxy, built with MkDocs Material.

## Building Documentation

### Install Dependencies

```bash
pip install -r docs_requirements.txt
```

### Serve Locally

```bash
mkdocs serve
```

Open http://127.0.0.1:8000

### Build Static Site

```bash
mkdocs build
```

Output will be in `site/` directory.

## Documentation Structure

```
docs/
├── index.md                 # Home page
├── installation.md          # Installation guide
├── quickstart.md            # Quick start guide
├── configuration.md         # Configuration reference
├── migration.md             # Migration guide (v2.x → v3.0)
├── troubleshooting.md       # Troubleshooting guide
├── development.md           # Development guide
├── api-reference.md         # Python API reference
├── docker.md                # Docker deployment
├── contributing.md          # Contributing guidelines
├── license.md               # License information
├── changelog.md             # Changelog
└── ebpf/                    # eBPF documentation
    ├── overview.md          # eBPF overview
    ├── setup.md             # Setup guide
    ├── architecture.md      # Architecture details
    └── performance.md       # Performance guide
```

## Contributing to Documentation

1. Edit markdown files in `docs/`
2. Preview with `mkdocs serve`
3. Submit PR with documentation changes

See [Contributing Guide](contributing.md) for details.

## Deployment

Documentation is automatically built and deployed to GitHub Pages on push to main branch.

## License

Documentation is licensed under MIT License, same as the code.
