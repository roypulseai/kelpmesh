# Installation

## Prerequisites

- Python 3.11 or later
- pip (Python package installer)

## Install from PyPI

```bash
pip install briq
```

## Install with extras

```bash
# Development tools (testing, linting, docs)
pip install "briq[dev]"

# Airflow integration
pip install "briq[airflow]"

# Full install for local development
pip install -e ".[dev]"
```

## Platform Support

briq works on Windows, macOS, and Linux.

## Verify Installation

```bash
briq --help
briq debug
```
