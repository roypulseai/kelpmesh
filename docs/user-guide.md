# KelpMesh User Guide

## What is KelpMesh?

KelpMesh is a **code-native data transformation tool** — like dbt or SQLMesh, but your model files are **plain SQL** (or Python). No Jinja templating, no special syntax to learn. If you know SQL, you already know KelpMesh.

```sql
-- dbt:  {{ config(materialized='table') }}{{ ref('orders') }} WHERE {{ is_incremental() }}
-- KelpMesh:
-- materialized: table
SELECT * FROM orders WHERE is_incremental()
```

KelpMesh works in three interfaces:

| Interface | Purpose |
|-----------|---------|
| **CLI** (`kelpmesh`) | All features — run, test, plan, build, diff, compile, security, CI/CD, scheduling |
| **Studio** (`kelpmesh studio`) | Browser dashboard — DAG visualization, run history, model overview (pair with CLI) |
| **VS Code Extension** | In-editor — CodeLens buttons, model tree, DAG/lineage webviews, snippets |

---

## Installation

```bash
pip install KelpMesh          # CLI only (free, Apache 2.0)
pip install kelpmesh-studio   # CLI + Studio dashboard (free for personal use)
```

Warehouse-specific extras:

```bash
pip install KelpMesh[postgres]    # Postgres/Redshift
pip install KelpMesh[snowflake]   # Snowflake
pip install KelpMesh[bigquery]    # BigQuery
pip install KelpMesh[databricks]  # Databricks
pip install KelpMesh[mysql]       # MySQL/MariaDB
pip install KelpMesh[trino]       # Trino/Presto
pip install KelpMesh[all-warehouses]  # all at once
```

DuckDB is the default (zero-install) warehouse — great for local development.

### VS Code Extension

Search **"KelpMesh"** in the VS Code extensions marketplace, or install from the `.vsix` attached to the [latest GitHub release](https://github.com/roypulseai/kelpmesh/releases).

---

## Quick Start Tutorial

### 1. Scaffold a project

```bash
kelpmesh init my_analytics
cd my_analytics
```

This creates:

```
my_analytics/
├── kelpmesh.yml          # project config
├── models/
│   └── example.sql       # example model (SELECT 1)
├── tests/
│   └── example.sql       # example test
├── macros/               # custom SQL macros
├── seeds/                # seed data (CSV → SQL)
└── .gitignore
```

### 2. Write your first model

Edit `models/my_first_model.sql`:

```sql
-- materialized: table
SELECT
    surrogate_key(customer_id, order_date) AS id,
    customer_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_revenue
FROM raw_orders
GROUP BY customer_id, order_date
```

### 3. Run it

```bash
kelpmesh run
```

This executes all models against your warehouse (DuckDB by default). Output shows each model's status, row count, and duration.

### 4. Preview data

```bash
kelpmesh preview my_first_model
```

Shows the first 100 rows as a formatted table.

### 5. Test it

```bash
kelpmesh test
```

Runs all assertion files in `tests/`. Each `.sql` file returns rows that failed the assertion — zero rows means the test passed.

### 6. Plan changes

```bash
kelpmesh plan
```

Shows a Terraform-style diff: which models will be created, skipped, or rebuilt. Safe to run anytime — it never writes to the warehouse.

### 7. Build (run + test)

```bash
kelpmesh build
```

Runs all models then runs all tests in one command.

---

## Project Structure

```
my_project/
├── kelpmesh.yml           # mandatory — project config
├── models/                # SQL and Python models
│   ├── staging/
│   │   ├── stg_orders.sql
│   │   └── stg_customers.sql
│   ├── marts/
│   │   └── daily_metrics.sql
│   └── snapshots/
│       └── scd_customers.sql
├── tests/                 # SQL assertion tests
│   ├── not_null_orders.sql
│   └── unique_customers.sql
├── macros/                # custom SQL macros
│   └── custom_functions.sql
├── seeds/                 # seed data
│   └── countries.sql
├── schema.yml             # model descriptions, column types, tags
├── sources.yml            # source table definitions + freshness
├── exposures.yml          # downstream consumers
├── metrics.yml            # semantic layer metrics
└── security.yml           # masking + RLS policies
```

### `kelpmesh.yml` Configuration

```yaml
name: my_project
warehouse:
  type: duckdb
  path: ./warehouse.db
target: dev
targets:
  dev:
    warehouse:
      type: duckdb
      path: ./dev.db
  prod:
    warehouse:
      type: postgres
      host: {{ env_var('PGHOST') }}
      database: analytics
      user: {{ env_var('PGUSER') }}
```

---

## Writing Models

### SQL Models (`.sql`)

SQL models use a **header comment** for metadata and **plain SQL** for the body:

```sql
-- materialized: incremental
-- unique_key: order_id
-- incremental_strategy: merge
-- description: Daily order summary table
-- tags: finance, daily

SELECT
    order_id,
    customer_id,
    order_date,
    status,
    total_amount
FROM raw_orders
{% if is_incremental() %}
WHERE order_date > (SELECT MAX(order_date) FROM {{ this }})
{% endif %}
```

**Available header fields:**

| Field | Description | Example |
|-------|-------------|---------|
| `materialized` | Materialization type | `table`, `view`, `incremental`, `snapshot`, `ephemeral` |
| `unique_key` | Dedup key for incremental/snapshot | `order_id` |
| `incremental_strategy` | Merge strategy | `merge`, `append` |
| `description` | Model description | `Daily order summary` |
| `tags` | Comma-separated tags | `finance, daily` |
| `cron` | Schedule expression | `0 6 * * *` |
| `enabled` | Enable/disable model | `true`, `false` |
| `time_column` | For incremental time filtering | `order_date` |
| `time_grain` | Time granularity | `day`, `hour` |
| `snapshot_strategy` | SCD Type 2 strategy | `timestamp` |
| `snapshot_updated_at` | Column tracking changes | `updated_at` |
| `hooks.pre` / `hooks.post` | SQL hooks | `GRANT SELECT ON {{ this }} TO analyst` |
| `contract.enforced` | Enforce column contracts | `true` |

### Python Models (`.py`)

```python
def model(dbt, session):
    dbt.config(materialized="table")
    df = session.sql("SELECT * FROM raw_orders")
    return df
```

The `dbt` parameter is a `DbtProxy` with `config()`, `ref()`, `source()`, `this` methods. The `session` parameter is a `SessionProxy` wrapping your warehouse connection. Return a pandas DataFrame or a SQL string.

### Jinja Templating

KelpMesh supports a minimal subset of Jinja for dynamic SQL. These work in both `.sql` and `.py` models:

| Expression | Purpose |
|-----------|---------|
| `{{ ref('model_name') }}` | Reference another model |
| `{{ source('source_name', 'table_name') }}` | Reference a source table |
| `{{ var('var_name', 'default') }}` | Project variable |
| `{{ env_var('NAME', 'default') }}` | Environment variable |
| `{{ this }}` | Current model's table name |
| `{% if is_incremental() %}...{% endif %}` | Incremental filter |
| `surrogate_key(col1, col2)` | MD5 hash key (used as plain SQL) |

### Built-in SQL Macros (32+)

Call these as **plain SQL functions** in any model — they expand at compile time:

**Identity:** `surrogate_key`, `hash_record`
**Math:** `safe_divide` / `div0`, `median`, `percentile`
**Date:** `datediff`, `dateadd`, `date_trunc`, `last_day`, `week_start`, `quarter_start`, `year_month`, `age_in_days`, `current_utc`
**String:** `initcap`, `regexp_extract`, `email_domain`, `phone_digits`, `left_pad`, `right_pad`, `contains`, `is_valid_email`, `url_extract_host`
**Conditional:** `iff`, `ifnull`, `zeroifnull`, `nullifzero`, `nullif_empty`, `coalesce_zero`
**Distance:** `haversine`

---

## Materializations

| Type | Behavior | Use Case |
|------|----------|----------|
| `view` | Creates a SQL view | Lightweight transformations, always fresh |
| `table` | Drops and recreates on each run | Small-to-medium datasets, full refresh |
| `incremental` | Merges new records since last run | Large datasets, append-only or upsert |
| `snapshot` | Type 2 slowly-changing dimension | Historical tracking of attribute changes |
| `ephemeral` | Inlined as CTE in dependent models | Reusable logic, never materialized |
| `analysis` | Compiled but not materialized | Documentation-only queries |

---

## CLI Command Reference

### Running Models

```bash
kelpmesh run                          # run all models
kelpmesh run --select stg_orders      # run specific model
kelpmesh run --select stg_orders+     # model + downstream
kelpmesh run --select +stg_orders     # model + upstream
kelpmesh run --select @stg_orders     # full subtree
kelpmesh run --select tag:finance     # all tagged models
kelpmesh run --changed                # only changed models (slim CI)
kelpmesh run --full-refresh           # force full rebuild
kelpmesh run --threads 8              # parallel execution
kelpmesh run --target prod            # switch target
kelpmesh run --defer                  # defer to prod state (skip unchanged)
```

### Testing

```bash
kelpmesh test                          # run all tests
kelpmesh test --select model_name      # test specific model
kelpmesh test --warn                   # treat failures as warnings
kelpmesh test --store-failures         # persist failing rows
kelpmesh test --generate               # generate expectation tests
```

### Building

```bash
kelpmesh build                         # run + test
kelpmesh build --select model_name     # build specific model
```

### Planning

```bash
kelpmesh plan                          # dry-run impact analysis
kelpmesh plan --select model_name      # plan for specific model
kelpmesh plan --full-refresh           # plan full rebuild
kelpmesh plan --json                   # machine-readable output
```

### Compiling

```bash
kelpmesh compile --select model_name   # show rendered SQL
kelpmesh compile --select model_name --print  # print to stdout
kelpmesh compile --select model_name --incremental  # render incremental SQL
```

### Documentation

```bash
kelpmesh docs                          # generate HTML docs
kelpmesh docs --serve                  # serve locally and open browser
kelpmesh docs manifest                 # generate manifest.json for tooling
```

### Diff & Compare

```bash
kelpmesh diff model_name               # compare model vs previous run
kelpmesh compare --dbt ./dbt-project   # compare kelpmesh vs dbt output
kelpmesh schema diff model_name        # detect schema drift
```

### History & Freshness

```bash
kelpmesh history orders                # show run history for a model
kelpmesh history --limit 20            # last 20 runs
kelpmesh freshness                     # check source table freshness
kelpmesh source freshness              # same, from source definitions
```

### Project Management

```bash
kelpmesh ls                            # list all models
kelpmesh clean                         # remove compiled artifacts
kelpmesh debug                         # validate project config + connection
kelpmesh generate raw_orders           # scaffold staging model from source table
kelpmesh seed                          # load seed data
kelpmesh format                        # auto-format SQL files
kelpmesh format --check                # CI check (exit 1 if unformatted)
kelpmesh lint                          # 10-rule SQL linter
kelpmesh lint --fix                    # auto-fix violations
```

### Dependencies

```bash
kelpmesh deps add kelpmesh-expectations   # add a package
kelpmesh deps remove kelpmesh-expectations # remove a package
kelpmesh deps install                      # install all deps
kelpmesh deps list                         # show installed
kelpmesh deps search expectations          # search registry
```

### Scheduling

```bash
kelpmesh schedule start                    # start cron scheduler
kelpmesh schedule start --daemon           # daemon mode (POSIX)
kelpmesh schedule stop                     # stop scheduler
kelpmesh schedule list                     # list schedules
kelpmesh schedule run nightly              # run named schedule now
```

### CI/CD

```bash
kelpmesh ci                                 # slim CI: diff → run → test → PR comment
kelpmesh ci --base main                     # compare against main branch
kelpmesh ci --defer                         # defer to prod state
kelpmesh ci --dry-run                       # preview without running
kelpmesh ci --post-comment                  # force PR comment
```

### Security

```bash
kelpmesh scan secrets                       # scan for hardcoded credentials
kelpmesh scan secrets --fail                # exit 1 if found (CI)
kelpmesh scan generate-key                  # generate Fernet encryption key
kelpmesh security classify --table orders   # classify PII columns
kelpmesh security classify --init           # create classify.yml
kelpmesh security mask orders --role viewer # preview column masking
kelpmesh security rls --init                # initialize RLS
kelpmesh security clean-pii --id-col email --id-value user@example.com  # GDPR erasure
kelpmesh security clean-pii --dry-run       # preview without deleting
kelpmesh security audit                     # view audit log
kelpmesh security status                    # overall security posture
kelpmesh security roles                     # list roles
```

### Data Mesh (Multi-Project)

```bash
kelpmesh mesh init --name platform          # scaffold mesh.yml
kelpmesh mesh validate                      # validate cross-project refs
kelpmesh mesh graph                         # print dependency graph
kelpmesh mesh status                        # health check all projects
kelpmesh mesh publish                       # publish interface.yml
```

### Migration

```bash
kelpmesh import ./dbt-project               # auto-detect and convert
kelpmesh import ./dbt-project --from dbt    # explicit
kelpmesh import ./sqlmesh-project           # auto-detect SQLMesh
kelpmesh migrate ./dbt-project              # interactive wizard
```

### Semantic Layer

```bash
kelpmesh metric list                        # list defined metrics
kelpmesh metric query total_revenue         # query a metric
kelpmesh metric query total_revenue --group-by region  # with dimensions
kelpmesh export --format looker             # export to LookML
kelpmesh export --format tableau            # export to Tableau TDS
kelpmesh export --format powerbi            # export to Power BI
kelpmesh serve                              # REST API for metrics
```

### Orchestration

```bash
kelpmesh orchestrate                        # run multiple projects in dependency order
```

### Miscellaneous

```bash
kelpmesh pre-commit                         # validate for pre-commit hooks
kelpmesh create-test model_name             # generate YAML fixture test from warehouse
kelpmesh rollback                           # force next full rebuild
kelpmesh rollback --steps 3                 # rollback N runs
kelpmesh studio                             # launch browser dashboard
kelpmesh version                            # show version
```

### Selection Syntax Reference

| Pattern | Selects |
|---------|---------|
| `model_name` | Exactly that model |
| `+model_name` | Model + all upstream dependencies |
| `model_name+` | Model + all downstream dependents |
| `+model_name+` | Full subtree (upstream + downstream) |
| `@model_name` | Model + all upstream + all downstream (full closure) |
| `tag:finance` | All models tagged `finance` |
| `stg_*` | All models starting with `stg_` |
| `--select source:raw_*` | All models referencing a source |

---

## KelpMesh Studio (Browser Dashboard)

**When to use:** When you want a visual overview of your project — DAG exploration, run history, model documentation — without leaving your browser.

### Launching

```bash
pip install kelpmesh-studio
kelpmesh studio
# Opens http://localhost:8765
```

### Features

**Overview Tab** — Project dashboard with:
- Model count and breakdown by materialization type
- Recent run history (status, elapsed time, row counts)
- Warehouse type and connection status

**Models Tab** — Grid of model cards with:
- Name and materialization badge (color-coded)
- Search and filter

**DAG Tab** — Interactive SVG lineage graph:
- Left-to-right topological layout
- Color-coded by materialization type (green=view, blue=table, yellow=incremental, purple=snapshot, teal=python)
- Click nodes to view model details
- Legend for materialization types

**Toolbar Actions:**
- **Run** — triggers `kelpmesh run` across all models
- **Plan** — triggers `kelpmesh plan` to preview changes
- **Refresh** — reloads project data

### When to Use Studio vs CLI

| Task | Use |
|------|-----|
| Explore model dependencies visually | **Studio** DAG tab |
| Check run history across all models | **Studio** History tab |
| Run all models ad-hoc | **Either** (Studio Run button or `kelpmesh run`) |
| Run a single model | **CLI** (`kelpmesh run --select model`) |
| Preview data | **CLI** (`kelpmesh preview model`) |
| Comprehensive CI/CD | **CLI** (`kelpmesh ci`) |
| Security operations | **CLI** (`kelpmesh security ...`) |
| Get a quick overview of project health | **Studio** Overview tab |

---

## VS Code Extension

**When to use:** When you're editing model files and want instant Run/Test/Preview/Build buttons, model tree navigation, and DAG visualization — all within your editor.

### Features

**CodeLens Buttons** — Appear above every `.sql` and `.py` file in `models/`:

| Button | Action |
|--------|--------|
| ▶ Run | `kelpmesh run --select <model>` |
| ⚗ Test | `kelpmesh test --select <model>` |
| 🚀 Build | `kelpmesh build --select <model>` |
| 👁 Preview | Shows 100 rows in a webview table |
| ⎇ Compile | Opens compiled SQL in side editor |
| 📖 Docs | Shows model documentation (description, columns, tags) |
| ⊞ Lineage | Opens interactive lineage view |

**Model Tree View** — Sidebar panel showing all models, grouped by materialization:

```
KelpMesh
├── Views (12)
│   ├── stg_orders
│   ├── stg_customers
│   └── ...
├── Tables (5)
│   ├── daily_metrics
│   └── ...
├── Incremental (3)
│   ├── orders_fact
│   └── ...
└── Python Models (2)
```

Click any model to open its file. Toolbar buttons: Refresh, Plan, Show DAG.

**DAG Webview** — Visual dependency graph:
- Search/filter models by name
- Color-coded by materialization
- Click nodes to open the model file
- Shows model count and filter state

**Lineage Webview** — Three display modes:
- **Cards** — Model cards with upstream/downstream dependency chips
- **DAG** — Interactive SVG dependency graph
- **Both** — Cards and graph side by side

**Status Bar** — Shows model count, updates during command execution, click to open DAG.

**SQL Snippets** — 27 autocomplete snippets for common patterns:
- `ref` → `{{ ref('model_name') }}`
- `source` → reference a source table
- `surrogate_key` → hash key function
- `is_incremental` → incremental filter block
- `datediff`, `dateadd`, `safe_divide`, `haversine`, and more

**Real-time Diagnostics** — Scans SQL files on open/change:
- Warns on hardcoded credentials
- Flags unclosed `{{ ref() }}` expressions

### Settings

| Setting | Description |
|---------|-------------|
| `kelpmesh.pythonPath` | Custom Python path (blank = workspace interpreter) |
| `kelpmesh.projectDir` | Project root path (blank = workspace root) |
| `kelpmesh.autoRunOnSave` | Auto-run model on file save |
| `kelpmesh.showCodeLens` | Show/hide CodeLens buttons |

### When to Use VS Code Extension vs Studio

| Task | Use |
|------|-----|
| Edit models with inline Run/Test buttons | **VS Code** |
| Browse all models in project tree | **VS Code** |
| Quick preview of model data | **VS Code** (Preview button) |
| View model documentation while editing | **VS Code** (Docs button) |
| Visual DAG exploration | **Either** (VS Code DAG webview or Studio DAG tab) |
| Full project dashboard | **Studio** |
| Run history across models | **Studio** |
| Large-screen DAG with filtering | **Studio** (better real estate) |
| Multi-project mesh management | **CLI** |

---

## Advanced Features

### Security & Compliance

KelpMesh includes a full security suite free in Core:

**PII Classification** — Auto-detect sensitive columns:
```bash
kelpmesh security classify --table orders
# Output: email → PII, ssn → restricted, ip_address → internal
```

**Column Masking** — Define role-based masking in `security.yml`:
```yaml
masking:
  orders:
    email:
      viewer: "REDACT"
      editor: "MASK_FIRST(4)"
      admin: "AS_IS"
```

**Row-Level Security** — Filter data per role:
```yaml
rls:
  orders:
    viewer: "region = current_user_region()"
```

**GDPR Erasure** — Purge a data subject across all models:
```bash
kelpmesh security clean-pii --id-col email --id-value user@example.com --dry-run
```

**Audit Log** — Immutable JSONL audit trail of all operations.

### CI/CD Integration

```bash
# In any CI pipeline:
kelpmesh ci
```

This single command:
1. Detects changed models (via git diff)
2. Plans the impact
3. Runs only changed models + downstream
4. Runs all tests
5. Posts a structured PR comment (GitHub/GitLab/Bitbucket)

CI configs are auto-generated at `kelpmesh init`:
- `.github/workflows/ci.yml`
- `.gitlab-ci.yml`
- `bitbucket-pipelines.yml`

### Scheduling

Built-in cron scheduler — no Airflow or external service required:

```yaml
# kelpmesh.yml
schedules:
  nightly:
    cron: "0 6 * * *"
    command: run --target prod
  hourly_metrics:
    cron: "0 * * * *"
    command: build --select hourly_metrics
```

```bash
kelpmesh schedule start         # start the scheduler
kelpmesh schedule start --daemon  # run as background process
```

### Data Mesh (Multi-Project)

For organizations with multiple KelpMesh projects:

```yaml
# mesh.yml
mesh:
  name: platform
  projects:
    - path: ./finance/
    - path: ./marketing/
      depends_on: [./finance/]
```

Cross-project references work like intra-project refs:
```sql
SELECT * FROM finance.daily_revenue  -- references model from finance project
```

### Semantic Layer

Define metrics in `metrics.yml`:
```yaml
metrics:
  total_revenue:
    type: sum
    sql: amount
    model: orders
    dimensions: [region, customer_tier]
```

Query via CLI:
```bash
kelpmesh metric query total_revenue --group-by region
# Returns: region | total_revenue
```

Or via REST API:
```bash
kelpmesh serve  # starts metrics API on port 7788
curl http://localhost:7788/metrics/total_revenue?group_by=region
```

Export to BI tools:
```bash
kelpmesh export --format looker    # LookML
kelpmesh export --format tableau   # Tableau TDS
kelpmesh export --format powerbi   # Power BI
```

---

## Migration from dbt

```bash
kelpmesh import ./my-dbt-project --output ./kelpmesh-project
```

What gets converted:

| dbt → KelpMesh |
|----------------|
| `{{ ref('model') }}` → plain table name |
| `{{ source('src', 'tbl') }}` → plain table name |
| `{{ config(materialized='table') }}` → `-- materialized: table` header |
| `schema.yml` (not_null, unique, etc.) → SQL assertion files |
| CSV seeds → SQL files with VALUES |
| Snapshots → SCD Type 2 model files |
| dbt packages → `kelpmesh deps add` equivalent |
| `dbt_utils` macros → built-in KelpMesh macros (`surrogate_key`, `safe_divide`, etc.) |

## Migration from SQLMesh

```bash
kelpmesh import ./my-sqlmesh-project --output ./kelpmesh-project
```

| SQLMesh → KelpMesh |
|--------------------|
| `MODEL (name ..., kind FULL)` → `-- materialized: table` |
| `INCREMENTAL_BY_UNIQUE_KEY` → `-- materialized: incremental, unique_key: ...` |
| `audits (...)` → SQL assertion files in `tests/` |
| `@execution_dt` → `CURRENT_DATE` |
| YAML unit test fixtures → smoke tests (regenerate with `kelpmesh create_test`) |

---

## Warehouse Support

| Warehouse | Extras | Install |
|-----------|--------|---------|
| DuckDB | Default, zero-install | Built-in |
| Postgres | — | `pip install KelpMesh[postgres]` |
| Redshift | — | `pip install KelpMesh[redshift]` |
| Snowflake | — | `pip install KelpMesh[snowflake]` |
| BigQuery | — | `pip install KelpMesh[bigquery]` |
| Databricks | — | `pip install KelpMesh[databricks]` |
| MySQL/MariaDB | — | `pip install KelpMesh[mysql]` |
| Trino/Presto | — | `pip install KelpMesh[trino]` |
| Microsoft Fabric | — | `pip install KelpMesh[fabric]` |
| ClickHouse | — | `pip install KelpMesh[clickhouse]` |
| Spark | — | `pip install KelpMesh[spark]` |
| Athena | — | `pip install KelpMesh[athena]` |
| SQL Server | — | `pip install KelpMesh[sqlserver]` |
| All | — | `pip install KelpMesh[all-warehouses]` |

---

## Integrations

| Tool | Integration |
|------|-------------|
| GitHub Actions | Built-in `ci.yml` template |
| GitLab CI | Built-in `.gitlab-ci.yml` template |
| Bitbucket Pipelines | Built-in `bitbucket-pipelines.yml` template |
| Dagster | `from kelpmesh_dagster import KelpMeshResource` |
| Prefect | `from kelpmesh_prefect import KelpMeshBlock` |
| Airflow | `pip install kelpmesh-airflow` (KelpMeshOperator) |
| VS Code | Extension from marketplace |
| pre-commit | `.pre-commit-hooks.yaml` included |

---

## Choosing Your Interface

```
┌─────────────────────────────────────────────────────────────────┐
│                    How to Work with KelpMesh                     │
├──────────────┬────────────────────┬─────────────────────────────┤
│  I want to…  │  Use this…         │  Why                        │
├──────────────┼────────────────────┼─────────────────────────────┤
│ Write models │ CLI + any editor   │ Any editor works (no lock-in)│
│              │ VS Code Extension  │ Snippets + CodeLens buttons │
├──────────────┼────────────────────┼─────────────────────────────┤
│ Run models   │ CLI                │ `kelpmesh run` is fastest   │
│              │ Studio Run button  │ One-click in browser        │
│              │ VS Code CodeLens   │ Run from editor toolbar     │
├──────────────┼────────────────────┼─────────────────────────────┤
│ View DAG     │ Studio DAG tab     │ Full-screen, searchable     │
│              │ VS Code DAG panel  │ In-editor, click→open model │
├──────────────┼────────────────────┼─────────────────────────────┤
│ CI/CD        │ CLI                │ `kelpmesh ci` in pipeline   │
├──────────────┼────────────────────┼─────────────────────────────┤
│ Security     │ CLI                │ `kelpmesh security ...`     │
├──────────────┼────────────────────┼─────────────────────────────┤
│ Schedule     │ CLI                │ `kelpmesh schedule start`   │
├──────────────┼────────────────────┼─────────────────────────────┤
│ Documentation│ CLI                │ `kelpmesh docs`             │
├──────────────┼────────────────────┼─────────────────────────────┤
│ Orchestrate  │ CLI                │ `kelpmesh orchestrate`      │
└──────────────┴────────────────────┴─────────────────────────────┘
```

**Rule of thumb:**
- **Daily work** = VS Code Extension (CodeLens + tree view + snippets)
- **Project analysis** = Studio (DAG + history + overview)
- **Automation** = CLI (CI/CD, scheduling, security, mesh)

---

## Getting Help

```bash
kelpmesh --help            # top-level help
kelpmesh run --help        # command-specific help
kelpmesh docs --serve      # browse generated docs
```

- [GitHub Issues](https://github.com/roypulseai/kelpmesh/issues)
- [Discord Community](https://discord.gg/dPAPDn4BF)
