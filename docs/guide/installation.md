# Installation

## Prerequisites

- Python 3.11 or later
- pip (Python package installer)

## Install from PyPI

```bash
pip install KelpMesh
```

## Install with extras

```bash
# Development tools (testing, linting, docs)
pip install "KelpMesh[dev]"

# Airflow integration
pip install "KelpMesh[airflow]"

# Full install for local development
pip install -e ".[dev]"
```

## Platform Support

KelpMesh works on Windows, macOS, and Linux.

## Verify Installation

```bash
KelpMesh --help
kelpmesh debug
```
