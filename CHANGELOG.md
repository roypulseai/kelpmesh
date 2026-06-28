# Changelog

All notable changes to briq are documented here.
Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Semantic Versioning](https://semver.org/).

---

## [0.2.0] — 2026-06-28

### Added — dbt Core parity + competitive differentiators

#### SQL transformation engine
- **`{{ var("name") }}`** — project-level and CLI `--var key=value` variable substitution
- **`{{ env_var("NAME") }}`** — environment variable substitution with optional default
- **`{{ is_incremental() }}`** — inline and block form (`{% if is_incremental() %}...{% endif %}`)
- **`{{ this }}`** — current model's resolved table name
- **Pre/post hooks** — `-- pre_hook: SQL` / `-- post_hook: SQL` comment headers; `{table}` placeholder
- **`-- enabled: false`** — skip a model without removing it from the project
- **Analyses directory** — `analyses/*.sql` files compile but are never materialized
- **Macro system** — `macros/*.sql` with dbt-compatible `{% macro name(args) %}...{% endmacro %}` syntax loaded at project init; built-in macros: `surrogate_key`, `safe_divide`, `date_trunc`, `datediff`, `current_timestamp`, `generate_schema_name`

#### CLI commands
- **`briq compile`** — render all substitutions and macros without touching the warehouse; writes to `target/compiled/`; `--print` streams to stdout
- **`briq plan`** — Terraform-style dry run: shows downstream impact (`+N models affected`), hook counts, tag labels; `--tag`, `--var`, `--json` flags
- **`briq run`** — added `--tag`, `--var`, `--full-refresh`
- **`briq seed`** — full rewrite: scans `seeds/*.csv`, infers column types (BOOLEAN / BIGINT / DOUBLE / DATE / TIMESTAMP / VARCHAR), supports `seeds/seeds.yml` schema overrides
- **`briq studio`** — uses bundled `briq.studio` app; no separate package required; auto-opens browser; requires `pip install briq[studio]`
- **`briq debug`** — per-field warehouse config validation with actionable error hints (wrong password, bad host, missing driver, SSL, timeout), macro and model count, telemetry guard, state summary

#### SCD Type 2 snapshots on all 7 warehouses
- Timestamp strategy — detects changes via `updated_at` column comparison
- Check strategy — compares all non-key columns with `IS DISTINCT FROM`
- Audit columns: `_scd_id`, `_valid_from`, `_valid_to`, `_is_current`, `_dbt_updated_at`
- Adapters without a snapshot implementation raise `NotImplementedError` explicitly — no silent SCD-2 data loss

#### Incremental merge on all 7 warehouse adapters
- DuckDB — `INSERT OR REPLACE`
- Postgres — `INSERT ... ON CONFLICT DO UPDATE SET`
- Snowflake — `MERGE INTO ... WHEN MATCHED THEN UPDATE`
- BigQuery — `MERGE` with backtick quoting
- Databricks — Delta Lake `MERGE INTO ... UPDATE SET * / INSERT *`
- Fabric (Microsoft) — T-SQL `MERGE` with semicolon terminator
- Redshift — `MERGE INTO` (Redshift 2022+)

#### New adapter: Amazon Redshift
- Postgres wire protocol, port 5439, `sslmode=require` by default
- Full incremental merge + SCD Type 2 snapshots

### Fixed
- Databricks incremental: was writing `CREATE OR REPLACE VIEW` instead of `CREATE TABLE` on first run
- Fabric T-SQL: `CREATE TABLE AS SELECT` is invalid — fixed to use `SELECT * INTO`
- Snapshot on non-DuckDB adapters previously fell through to a plain table rebuild without any error — now raises `NotImplementedError` to prevent silent data corruption
- `briq plan` output truncated model names in narrow terminals

### Changed
- `pyproject.toml`: author updated to Saikat Roy (`saikatxtreme@gmail.com`); warehouse drivers split into per-adapter optional extras (`briq[postgres]`, `briq[snowflake]`, `briq[bigquery]`, `briq[databricks]`, `briq[fabric]`, `briq[redshift]`); `briq[all-warehouses]` meta-extra installs all drivers at once
- `briq.yml` now supports a `macros_path` field (default: `macros/`)
- `briq studio` no longer requires a separately installed `briq_studio` package — Studio is now bundled in `briq.studio`

### Tests
- 530 tests passing across 25 test files
- New: `test_substitutions.py` (27 tests), `test_hooks.py` (6), `test_tag_selection.py` (7), `test_seeds_v2.py` (16), `test_analyses.py` (5), `test_compile.py` (9), `test_adapters_incremental.py` (24)

---

## [0.1.0] — 2026-05-15

### Added
- Initial release: DuckDB, Postgres, Snowflake, BigQuery, Databricks, Fabric adapters
- `briq run`, `briq test`, `briq build`, `briq diff`, `briq docs`, `briq seed`, `briq preview`
- DAG-based model execution with topological sort and parallel threading
- State engine (DuckDB-backed hash store) for incremental re-runs
- Security subsystem: PII scanning, RLS policies, audit log, secret scanning
- Semantic layer: sources, exposures, metrics, BI export
- Schema drift detection (`briq schema diff`)
- `briq plan` — Terraform-style dry run (initial version)
- Project mesh: cross-project refs, access control, contracts
- briq Studio: browser-based IDE (bundled in `briq[studio]`)
