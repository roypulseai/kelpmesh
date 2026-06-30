# Migration from dbt

KelpMesh can automatically convert dbt projects to pure SQL. The import process
converts Jinja macros, preserves materializations, copies seeds, and generates
assertion tests from schema.yml.

## Quick Start

`ash
# Import a dbt project
kelpmesh import ./my-dbt-project --output ./my-kelpmesh-project

# Or use the interactive migration wizard
kelpmesh migrate ./my-dbt-project --output ./my-kelpmesh-project

# Then run the imported project
cd my-kelpmesh-project
kelpmesh debug          # validate config
kelpmesh plan           # check the DAG
kelpmesh seed           # load seed data
kelpmesh run            # execute all models
kelpmesh test           # run generated tests
`

## What Gets Converted

| dbt Feature | KelpMesh Equivalent |
|-------------|---------------------|
| `{{ ref('model') }}` | Plain table name (auto-resolved by AST) |
| `{{ source('schema', 'table') }}` | Plain table name |
| `{{ config(materialized='table') }}` | `-- { materialized: table }` header |
| `{{ cents_to_dollars('col') }}` | `(col / 100)::numeric(16, 2)` |
| `{{ dbt.date_trunc('day', col) }}` | `DATE_TRUNC('day', col)` |
| `{{ dbt_utils.generate_surrogate_key(['a','b']) }}` | `generate_surrogate_key(a, b)` |
| `{{ is_incremental() }}` | `TRUE` (use `-- materialized: incremental` header) |
| `{{ var('name', 'default') }}` | `'default'` (literal value) |
| `{{ env_var('VAR', 'default') }}` | `'default'` (literal value) |
| schema.yml tests (not_null, unique, etc.) | `tests/*.sql` assertion queries |
| Seeds (CSV) | Preserved as CSV + .sql wrapper |
| Sources (sources.yml) | Preserved + ephemeral model stubs |
| Snapshots | `-- { materialized: table, strategy: snapshot }` |
| Analyses | `-- { materialized: ephemeral }` |
| dbt_project.yml folder configs | Per-model `-- materialized:` headers |

## dbt-Compatible Macros (Runtime)

KelpMesh includes 12 dbt-compatible macros that work as plain SQL function calls
(no Jinja). These are available at runtime in any kelpmesh model:

| dbt Macro | KelpMesh SQL | Example |
|-----------|-------------|---------|
| `cents_to_dollars(col)` | `(col / 100)::numeric(16, 2)` | `SELECT cents_to_dollars(revenue_cents)` |
| `dollars_to_cents(col)` | `(col * 100)::bigint` | `SELECT dollars_to_cents(price)` |
| `dbt_current_timestamp()` | `CURRENT_TIMESTAMP` | `SELECT dbt_current_timestamp()` |
| `dbt_type_string()` | `'VARCHAR'` | `CAST(col AS dbt_type_string())` |
| `dbt_type_numeric()` | `'DECIMAL'` | Type macro |
| `dbt_type_bigint()` | `'BIGINT'` | Type macro |
| `dbt_type_timestamp()` | `'TIMESTAMP'` | Type macro |
| `dbt_type_date()` | `'DATE'` | Type macro |

Plus 32 built-in macros: `surrogate_key`, `safe_divide`, `datediff`,
`dateadd`, `date_trunc`, `haversine`, `median`, `percentile`, and more.

## Migration Report

After import, a `MIGRATION_REPORT.md` is generated in the output directory listing:

- Imported models and their materializations
- Folder-level materialization overrides (from dbt_project.yml)
- Leftover Jinja macros requiring manual review
- Next steps

## Interactive Migration Wizard

`ash
kelpmesh migrate ./my-dbt-project
`

This wizard:
1. Scans the dbt project (counts models, seeds, tests, packages, snapshots)
2. Reports what was found
3. Asks for confirmation
4. Runs the full import with macro conversion
5. Generates MIGRATION_REPORT.md

Use `--yes` / `-y` for non-interactive mode (CI/CD):

`ash
kelpmesh migrate ./my-dbt-project --yes -o ./kelpmesh-project
`

## dbt-Compatible Project Layout

Start a new project with a dbt-style directory structure:

`ash
kelpmesh init my_project --compat dbt
`

This creates:
- `models/staging/` — stg_ models (views)
- `models/marts/` — business marts (tables)
- `models/intermediate/` — intermediate transformations

## Row-by-Row Comparison Against dbt

During migration, compare kelpmesh output against dbt:

`ash
# First, compile dbt so target/ exists
cd ./my-dbt-project && dbt build

# Then compare
kelpmesh compare orders --dbt ./my-dbt-project
`

If dbt hasn't been compiled, kelpmesh will tell you to run `dbt build` first.

## Why Migrate?

| Feature | dbt | KelpMesh |
|---------|-----|----------|
| Model syntax | Jinja-templated SQL | Pure SQL (no Jinja) |
| IDE autocomplete | Broken by Jinja | Full |
| AI assistant support | Broken by Jinja | Full |
| Column lineage | Enterprise only | Free |
| Schema drift detection | Manual | Built-in |
| Audit logging | Not included | Built-in |
| Security (RLS, masking, erasure) | Not included | Built-in suite |
| Learning curve | Weeks | Minutes |
| CI/CD (PR comments) | dbt Cloud only | Free, self-hosted |
| Price | Free-/mo | Free (core) / /mo (studio) |

## Manual Review Items

After import, some items may need manual attention:

1. **Untranslated Jinja macros** — listed in MIGRATION_REPORT.md. Run `kelpmesh plan`
   to see which models have parse errors, then replace the remaining `{{ }}` blocks
   with plain SQL.

2. **dbt packages** — Common macros from dbt_utils and dbt_date are auto-converted.
   Custom package macros need manual porting to `macros/*.py` or `macros/*.yml`.

3. **Metricflow / dbt metrics** — These are not auto-converted. Define metrics
   manually in `metrics.yml`.

4. **Python models** — dbt Python models need to be adapted to the kelpmesh
   `def model(dbt, session)` interface.