# Changelog

All notable changes to briq are documented here.
Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Semantic Versioning](https://semver.org/).

---

## [0.2.0] — 2026-06-28

### Added
- **Security suite** — audit logging, column masking, row-level security (RLS), data classification, PII erasure, secrets scanning, and transparent AES-256-GCM encryption at rest
- **27 CLI commands** — run, test, build, diff, preview, ls, clean, debug, compare, deps, orchestrate, pre-commit, docs, docs-manifest, import, seed, schema diff, scan secrets, security (audit/classify/mask/rls/clean-pii/status/roles), source, exposure, metric, package
- **Live progress output** for `briq run` and `briq build` — each model prints as it completes with timing
- **Model execution timing** — elapsed time per model reported in run/build output
- **Parallel executor** with DuckDB connection pooling (`ConnectionPool`) — `--threads` flag on `briq run` and `briq build`
- **Schema drift detection** — `briq schema diff` compares stored vs current column signatures
- **Column-level lineage** in `briq docs` — every column card shows upstream source columns
- **Incremental models** with merge and append strategies for DuckDB
- **Python models** — define a `model()` function returning a DataFrame or DuckDB relation
- **`briq import --from dbt`** — full migration of models, refs, sources, config blocks, seeds, snapshots, YAML tests, and schema.yml
- **Node selection syntax** — `+model` (with upstream), `model+` (with downstream), `@model` (full subgraph)
- **Slim CI** — `briq run --changed` runs only models changed vs the base branch
- **Deferral** — `briq run --defer <prod-state>` skips models whose hash matches production
- **`briq-utils`** and **`briq-expectations`** SQL packages in `briq_packages/`
- **VS Code extension** skeleton with CodeLens run/test/preview/lineage buttons
- **Airflow integration** — `BriqOperator` and `BriqDag` in `extensions/airflow/`
- **briq Studio** scaffold — FastAPI backend + frontend in `extensions/studio/`
- **GitHub Actions CI template** and **GitLab CI template**
- **Pre-commit hook** — `briq-validate` checks SQL syntax before commit
- **`briq compare --dbt`** — compare briq vs dbt output during migration
- **`briq orchestrate`** — lightweight built-in scheduler
- **`briq deps`** — show full upstream/downstream dependency tree
- **Microsoft Fabric adapter** stub
- **Databricks adapter** stub

### Fixed
- Windows cp1252 encoding: `sys.stdout.reconfigure(encoding="utf-8")` + `PYTHONUTF8=1` at startup
- `briq preview` column style — first column now correctly highlighted cyan
- `briq preview` null values rendered as `null` instead of the string `"None"`

### Changed
- `briq run` and `briq build` now print each model as it completes rather than a static table at the end
- State engine uses WAL mode for safer concurrent reads
- Publish workflow uses `python -m build` (PEP 517 standard) instead of `hatchling build` directly

---

## [0.1.0] — 2026-06-01

### Added
- Initial working CLI POC — `init`, `run`, `test`, `build`, `diff`, `docs`, `import`, `seed`
- sqlglot-based SQL AST parser with automatic dependency resolution
- networkx DAG builder with topological execution order and cycle detection
- DuckDB adapter (persistent file-based) with full create/view/table/incremental support
- DuckDB-backed state engine — model hash tracking, skip-unchanged
- Static HTML documentation generator with per-model cards and lineage links
- `briq import` — strips `{{ ref() }}`, `{{ source() }}`, `{{ config() }}`, `{{ this }}` from dbt models
- Sequential executor
- 25 unit tests across parser, graph, project, state
- Sample project with 4 models and 3 SQL assertion tests
