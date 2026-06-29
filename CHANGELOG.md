# Changelog

All notable changes to KelpMesh are documented here.
Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Semantic Versioning](https://semver.org/).

---

## [1.0.0] — 2026-06-29

### 🎉 First stable release — kelpmesh-core 1.0.0

### Added
- 14 warehouse adapters: DuckDB, PostgreSQL, Snowflake, BigQuery, Databricks, Redshift, Microsoft Fabric, MySQL, Trino, ClickHouse, Apache Spark, Amazon Athena, Apache Hive, SQL Server / Azure Synapse
- 7 materialisation types: view, table, incremental (merge/append), incremental\_by\_time\_range, ephemeral, snapshot (SCD2), materialized\_view
- Model contracts — column name + type enforcement post-run
- Model versioning — `-- version: N` with automatic latest-version routing
- grain: / audits: — post-run uniqueness and data quality checks
- Environment rollback — `kelpmesh rollback` clears state for rebuild
- `kelpmesh format` — sqlglot-powered SQL auto-formatter with `--check` CI mode
- `kelpmesh lint` — 10-rule SQL linter (L001–L010)
- Full rename: all internal identifiers migrated from `briq` → `kelpmesh`
- Published under the RoyPulseAI GitHub / PyPI identity

---

## [0.3.0] — 2026-06-28

### Added — Full platform: macros, Python models, CI/CD, freemium Studio

#### SQL macros — SQL-native, zero Jinja

32 built-in macros callable as plain SQL functions (expanded at compile time):

- **String:** `surrogate_key`, `generate_surrogate_key`, `safe_cast`, `slugify`, `truncate_string`
- **Numeric:** `safe_divide`, `round_half_up`, `sign`
- **Date/time:** `datediff`, `date_trunc_week`, `date_spine`, `current_timestamp_utc`, `to_unix_timestamp`, `from_unix_timestamp`, `fiscal_year`, `fiscal_quarter`, `age_in_years`, `months_between`
- **Geography:** `haversine`
- **Type detection:** `is_numeric_string`, `is_valid_email`, `is_valid_url`, `is_valid_date`
- **Array/set:** `array_to_string`, `string_to_array`, `deduplicate_array`
- **Conditional:** `coalesce_cast`, `nullif_zero`, `zero_if_null`, `greatest_not_null`, `least_not_null`
- **Warehouse utility:** `generate_schema_name`, `limit_rows`

Macros are plain SQL — no `{{ }}` syntax, fully compatible with IDE autocomplete and AI tools.

#### Python models

- `def model(dbt, session)` interface; return SQL string, pandas DataFrame, or None (no-op)
- `DbtProxy` — `.ref()`, `.source()`, `.config()` helpers for Python models
- `SessionProxy` — warehouse-agnostic query execution (wraps the active adapter)
- Mixed projects supported — SQL and Python models in the same DAG

#### New warehouse adapters

- **MySQL** — `mysql+mysqlconnector://` connection string, full incremental merge, SCD Type 2
- **Trino** — HTTP/HTTPS connection, catalog-qualified identifiers, full incremental merge

Total adapters: DuckDB · Postgres · Snowflake · BigQuery · Databricks · Redshift · Microsoft Fabric · MySQL · Trino (9 total)

#### Built-in cron scheduler

- `kelpmesh schedule add "0 6 * * 1-5" kelpmesh build` — no Airflow needed
- `kelpmesh schedule list` — show all registered schedules with next-run time
- `kelpmesh schedule start` — runs all schedules as a long-running process
- `kelpmesh schedule remove <name>` — deregister a schedule
- Custom parser supports both cron syntax (`0 6 * * 1-5`) and interval syntax (`every 1h`, `every 30m`)
- Zero external dependencies — pure Python using `threading.Timer`

#### Orchestration integrations

- **Dagster** — `KelpMeshResource`, `@kelpmesh_asset`, `KelpMeshOp`, `KelpMeshSchedule`, `run_freshness_sensor`
- **Prefect** — `KelpMeshBlock`, `kelpmesh_run_task`, `kelpmesh_build_flow` pre-built flow
- Both integrations use direct Python API calls (not subprocess) for structured result capture

#### CI/CD — `kelpmesh ci`

- `kelpmesh ci` — single command: detect changed models → compute downstream plan → run → test → post PR comment
- Slim CI by default: only runs models changed vs `base_branch` (git diff)
- `--dry-run` — plan and report without executing any models
- `--select` — limit to specific models or tags
- `--defer` — skip unchanged models whose production state matches current hash
- `--no-comment` — suppress PR comment (for non-PR branches)
- `--json` — write structured `CIReport` to file for downstream use
- `--fail-on-test` / `--no-fail-on-test` — control exit code on test failures

#### GitHub / GitLab / Bitbucket integrations (zero added dependencies)

- Auto-detects VCS provider from environment variables
- **GitHub** — posts/updates PR comment via GitHub REST API; idempotent (updates existing `<!-- kelpmesh-ci -->` marker)
- **GitLab** — posts/updates MR note; uses `CI_MERGE_REQUEST_IID`
- **Bitbucket** — posts PR comment via Bitbucket Cloud API
- All three use stdlib `urllib` only — no `requests`, no `httpx`

#### CI templates

- **`.github/workflows/ci.yml`** — updated: `pull-requests: write` permission, slim CI on PR, full matrix build on push to main
- **`.github/actions/kelpmesh-build/action.yml`** — updated: wraps `kelpmesh ci`; inputs: `slim-ci`, `base-branch`, `defer-state`, `dry-run`, `post-comment`
- **`.gitlab-ci.yml`** — new: four stages: `kelpmesh:scan` (pre), `kelpmesh:ci` (MR), `kelpmesh:build` (push to main), `kelpmesh:nightly` (scheduled)
- **`bitbucket-pipelines.yml`** — new: pull-request, main/master branch, and nightly pipelines

#### Studio — freemium licensing

- Four tiers: Free (personal, 1 user, 3 projects) / Pro ($29/user/mo) / Business ($79/user/mo) / Enterprise
- Local license validation — `km_<tier>_<b64url(payload)>_<hmac8>` codec; no phone-home
- `KELPMESH_STUDIO_TIER` env var → `KELPMESH_STUDIO_LICENSE_KEY` env var → `kelpmesh.yml` → default free
- FastAPI dependency injection for all gated endpoints (`Depends(_lic.require_feature(...))`)
- `GET /api/tier` endpoint returns current tier info
- Project creation enforces `max_projects` limit per tier
- Run history capped at `max_run_history` per tier
- User management and schedule management gated on Pro+ tier

#### VS Code extension rewrite

- 37 SQL snippets covering all materializations, macros, security, and mesh patterns
- Model tree view in sidebar with status icons
- CodeLens buttons: Run · Test · Preview · Plan (per model)
- Plan panel — shows downstream impact before running
- Source/test/snapshot file type registration

#### Package split

- `kelpmesh-core` (Apache 2.0, always free) — CLI engine, adapters, macros, security, CI/CD, scheduler
- `kelpmesh-studio` (freemium) — Core + FastAPI browser layer with licensing
- `pip install kelpmesh-studio` installs Core as a dependency; Studio is strictly a superset

#### Data mesh (Phase F)

- Cross-project `ref('project_b', 'model')` — references across repo boundaries
- `access: public | protected | private` on model declarations
- Column-level contracts: upstream publishes interface; downstream pins to it
- Multi-warehouse mesh: Project A on Snowflake, Project B on BigQuery

#### Semantic layer (Phase E)

- Metric YAML definitions: `name`, `label`, `type` (simple/ratio/cumulative), `measure`, `dimensions`
- `kelpmesh metric query` — SQL generation from metric + dimension + filter at query time
- Saved queries — pre-materialized metric + dimension combos as views
- BI export: LookML, Tableau `.tds`, PowerBI `.pbit`, Qlik

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
- **`kelpmesh compile`** — render all substitutions and macros without touching the warehouse; writes to `target/compiled/`; `--print` streams to stdout
- **`kelpmesh plan`** — Terraform-style dry run: shows downstream impact (`+N models affected`), hook counts, tag labels; `--tag`, `--var`, `--json` flags
- **`kelpmesh run`** — added `--tag`, `--var`, `--full-refresh`
- **`kelpmesh seed`** — full rewrite: scans `seeds/*.csv`, infers column types (BOOLEAN / BIGINT / DOUBLE / DATE / TIMESTAMP / VARCHAR), supports `seeds/seeds.yml` schema overrides
- **`kelpmesh debug`** — per-field warehouse config validation with actionable error hints, macro and model count, telemetry guard, state summary

#### SCD Type 2 snapshots on all 7 warehouses
- Timestamp strategy — detects changes via `updated_at` column comparison
- Check strategy — compares all non-key columns with `IS DISTINCT FROM`
- Audit columns: `_scd_id`, `_valid_from`, `_valid_to`, `_is_current`, `_dbt_updated_at`

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
- Snapshot on non-DuckDB adapters previously fell through to a plain table rebuild — now raises `NotImplementedError`
- `kelpmesh plan` output truncated model names in narrow terminals

### Changed
- `pyproject.toml`: author updated to Roy Pulse AI (`roypulse.ai@gmail.com`); warehouse drivers split into per-adapter optional extras; `kelpmesh[all-warehouses]` meta-extra installs all drivers
- `kelpmesh.yml` now supports a `macros_path` field (default: `macros/`)

### Tests
- 530 tests passing across 25 test files
- New: `test_substitutions.py` (27), `test_hooks.py` (6), `test_tag_selection.py` (7), `test_seeds_v2.py` (16), `test_analyses.py` (5), `test_compile.py` (9), `test_adapters_incremental.py` (24)

---

## [0.1.0] — 2026-05-15

### Added
- Initial release: DuckDB, Postgres, Snowflake, BigQuery, Databricks, Fabric adapters
- `kelpmesh run`, `kelpmesh test`, `kelpmesh build`, `kelpmesh diff`, `kelpmesh docs`, `kelpmesh seed`, `kelpmesh preview`
- DAG-based model execution with topological sort and parallel threading
- State engine (DuckDB-backed hash store) for incremental re-runs
- Security subsystem: PII scanning, RLS policies, audit log, secret scanning
- Semantic layer: sources, exposures, metrics, BI export
- Schema drift detection (`kelpmesh schema diff`)
- `kelpmesh plan` — Terraform-style dry run (initial version)
- Project mesh: cross-project refs, access control, contracts
- KelpMesh Studio: browser-based IDE (bundled in `kelpmesh[studio]`)
