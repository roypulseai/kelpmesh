# Changelog

## 1.0.3 (unreleased)

### Added
- `kelpmesh --version` flag
- `import kelpmesh_core` alias shim
- Quick Start panel in `kelpmesh --help` (init, seed, run, test)
- Usage examples on 20+ CLI commands
- `__all__` + docstrings on all 18 `__init__.py` files
- Exception hierarchy: `ConfigError`, `ModelError`, `WarehouseConnectionError`
- Changelog and Contributing guide
- Docs reorganized: `kelpmesh docs manifest` replaces `kelpmesh docs-manifest`

### Fixed
- Import aliases: `DAG = DAGBuilder`, `Classifier = DataClassifier`
- All major constructors accept `None` defaults for REPL exploration
- Module-level imports no longer leak into public namespace (`__all__` everywhere)
- `from __future__` import ordering in macros, fixtures, substitutions modules

### Changed
- CLI help organized into panels: Quick Start, Commands, Analysis, Quality, Integrations
- Sub-app help strings list available subcommands
- `init` next-steps now suggest `debug` and `seed` before `run`

## 1.0.2

### Fixed
- CI workflow: `pip install -e .` replaces `pip install kelpmesh-core`
- 17 test failures in billing, pricing, studio tests
- Ruff lint: 298 issues → 0

### Added
- `__version__` attribute
- Top-level public API re-exports (`__all__` in `kelpmesh/__init__.py`)
- CLI descriptions for all 39 commands
- Encoding fix for garbled CLI character

## 1.0.1

### Fixed
- Constructor defaults for `SchemaYaml`, `DataClassifier`
- Import aliases: `KelpMeshError`, `CryptoEngine`, `SubstitutionEngine`, `PythonParser`, `Comparer`, `Fixture`, `Scheduler`
- License classifiers and metadata

## 1.0.0

Initial release.
