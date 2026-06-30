# Contributing to KelpMesh

## Development Setup

```bash
git clone https://github.com/RoyPulseAI/kelpmesh.git
cd kelpmesh
pip install -e ".[dev,studio,all-warehouses]"
```

## Running Tests

```bash
pytest                           # all tests
pytest tests/ -x -q             # fast feedback, stop on first failure
pytest tests/test_phase_a.py    # single file
pytest -k "test_run"            # by name
```

## Linting

```bash
ruff check .
ruff format --check .
```

## Code Style

- Line length: 140
- Type hints required on all public functions
- `__all__` required in every `__init__.py`
- `from __future__ import annotations` at top of file where used
- Document public API with docstrings and usage examples

## Adding a CLI Command

1. Create the command function in `kelpmesh/cli/<name>.py`
2. Add a docstring with description and `Examples:` section
3. Register it in `kelpmesh/cli/main.py` with `app.command()`
4. Assign a `rich_help_panel` for `--help` organization

## Versioning

We follow [SemVer](https://semver.org/). Before releasing:

1. Update `__version__` in `kelpmesh/__init__.py`
2. Update `version` in `pyproject.toml` and `recipe/meta.yaml`
3. Run the full test suite
4. Update `CHANGELOG.md`
5. Tag with `v<version>` and push

## Publishing

Releases are published automatically via GitHub Actions when a GitHub Release is created. The workflow builds the package and publishes to PyPI using trusted publishing (OIDC).

## Questions

Open an issue at https://github.com/RoyPulseAI/kelpmesh/issues
