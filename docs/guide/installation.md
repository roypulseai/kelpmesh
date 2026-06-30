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
kelpmesh --help
kelpmesh debug
```

### Windows PATH fix

If `kelpmesh` is not recognized after installation, your Python Scripts directory is not on `PATH`. Add it with:

```powershell
$scripts = (Get-Command python -ErrorAction SilentlyContinue).Source | Split-Path
$scripts = Join-Path $scripts "Scripts"
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$scripts*") {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$scripts", "User")
    Write-Host "Added $scripts to PATH. Restart your terminal."
}
```
