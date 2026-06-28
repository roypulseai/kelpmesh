# Contributing to briq

We love contributions! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/briq-dev/briq
cd briq
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

## Running Tests

```bash
python -m pytest tests/
```

## Code Style

- Format: `ruff format .`
- Lint: `ruff check .`
- Type-check: `mypy briq/`

## Pull Request Process

1. Open an issue first to discuss the change.
2. Write tests for any new functionality.
3. Ensure all tests pass (`pytest tests/ -v`).
4. Update the CLI reference in `site/index.html` if adding commands.
5. Run `briq pre-commit` to validate SQL parsing.

## Commit Messages

Use conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, etc.

## Code of Conduct

Please note our [Code of Conduct](CODE_OF_CONDUCT.md). Be kind, be professional.
