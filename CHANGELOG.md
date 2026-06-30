# Changelog

## 1.0.5 (unreleased)

### Added
- Python model documentation and legacy Jinja macros support in user guide
- Enhanced L002 lint messages for better model/source/seed identification
  - Source tables: `use source('source_name', 'table_name') instead`
  - Seed tables: `use source('seeds', 'table_name') instead`
  - Unknown tables: `use ref('table_name') instead`

### Fixed (1.0.4 fixes incorporated)
- Timing display: show `<0.01s` instead of `0.00s` for sub-millisecond models (`run`, `build`, `history`)
- DuckDB init template: added `warehouse.path` so seed data persists across runs
- Linter L002-L010: skip seed/source files to eliminate false positives
- State DB lock: close defer state engine in `Executor.run()` finally block
- Preview: column headers no longer truncated (`overflow="fold"`)
- DuckDB pool semaphore leak: `release()` always decrements semaphore
- CLI tables: added `overflow="fold"` to Notes, Upstream, Downstream, Description, Detail, Message, Command columns

## 1.0.4

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

## 1.0.3

### Fixed
- CI workflow: `pip install -e .` replaces `pip install kelpmesh-core`
- 17 test failures in billing, pricing, studio tests
- Ruff lint: 298 issues → 0

### Added
- `__version__` attribute
- Top-level public API re-exports (`__all__` in `kelpmesh/__init__.py`)
- CLI descriptions for all 39 commands
- Encoding fix for garbled CLI character
- Python model support via `PythonModelRunner`
- `session.execute()` and `session.execute_df()` helpers for in-model SQL execution

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
- Python model support via `PythonModelRunner`
- `session.execute()` and `session.execute_df()` helpers for in-model SQL execution

## 1.0.1

### Fixed
- Constructor defaults for `SchemaYaml`, `DataClassifier`
- Import aliases: `KelpMeshError`, `CryptoEngine`, `SubstitutionEngine`, `PythonParser`, `Comparer`, `Fixture`, `Scheduler`
- License classifiers and metadata

## 1.0.0

Initial release.