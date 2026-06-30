# Changelog
## 1.0.6

### Fixed (field-test feedback from jaffle-shop migration)
- **CTE parser false circular dependencies** — CTE aliases (e.g. WITH orders AS (...)) no longer create outgoing dependency edges; prevents false cycle detection when a CTE name collides with a real model name (kelpmesh/parser/sql.py)
- **.sql seeds don't create tables** — bare SELECT/WITH seed files are now auto-wrapped in CREATE OR REPLACE TABLE <name> AS ... so imported seeds actually persist as queryable tables (kelpmesh/cli/seed.py)
- **Jinja macros not converted during import** — added _convert_dbt_macros() translator for cents_to_dollars, dbt.date_trunc, dbt_utils.generate_surrogate_key, dbt_utils.safe_divide, is_incremental, dbt_date.get_base_dates; fixes 9/12 models in jaffle-shop import (kelpmesh/cli/import_dbt.py)
- **Materialization configs not preserved** — kelpmesh import now parses dbt_project.yml models: section for per-folder +materialized: configs and emits -- materialized: table/view headers on imported models
- **SchemaYaml empty after import** — now scans ALL .yml/.yaml files with a models: or sources: key, not just literal schema.yml filenames (kelpmesh/core/schema_yaml.py)
- **compare --dbt silent failure** — pre-flight check: clear error if dbt 	arget/ doesn't exist instead of confusing catalog error (kelpmesh/cli/compare.py)
- **preview rendering on Windows PowerShell** — legacy_windows=False for proper rich table grid rendering (kelpmesh/cli/preview.py)
- **security classify --table flag** — added --table/-t option alias for the positional table argument (kelpmesh/cli/security.py)
- **Windows state DB file lock** — retry with 0.4s sleep (5 attempts) in kelpmesh clean to handle briefly-held DuckDB file locks (kelpmesh/cli/clean.py)

### Added
- **dbt_compat macro library** — 12 new runtime macros (44 total): cents_to_dollars, dollars_to_cents, dbt_current_timestamp, dbt_now, dbt_type_string/numeric/bigint/int/timestamp/date/boolean/float — usable as plain SQL function calls, no Jinja (kelpmesh/core/macros.py)
- **Interactive kelpmesh migrate wizard** — scans dbt project, reports stats (models, seeds, tests, packages, Jinja count), asks for confirmation, runs full import, generates MIGRATION_REPORT.md; --yes flag for non-interactive CI/CD (kelpmesh/cli/import_dbt.py)
- **--compat dbt flag for kelpmesh init** — generates dbt-style directory layout (models/staging/, models/marts/, models/intermediate/) with staging + mart examples (kelpmesh/cli/init.py)
- **Migration report** — MIGRATION_REPORT.md auto-generated after import listing imported models, materialization overrides, leftover Jinja macros needing manual review, and next steps
- **CSV seed preservation** — original .csv files preserved alongside .sql wrappers during import so kelpmesh seed loads them natively via ead_csv_auto
- **Schema YAML preservation** — schema.yml and any *.yml declaring models are copied into the output models/ dir so descriptions/column metadata survive import
- **Sources preservation** — original sources.yml copied into output project so kelpmesh source list works after import
- **Migration docs** — complete rewrite of docs/migration/from-dbt.md with macro translation table, wizard usage, --compat dbt layout, comparison instructions, and manual review checklist

### Changed
- kelpmesh import now auto-converts Jinja macros, preserves materializations, keeps CSV seeds, copies schema YAML, and generates a migration report — the dbt migration path is now one-command for most projects
- Built-in macro count: 32 → 44

## 1.0.5

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