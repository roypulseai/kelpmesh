# Models

Models are the core building block in KelpMesh. Each model is a `.sql` file containing a `SELECT` statement that KelpMesh materializes in your warehouse.

## Model basics

Models live under `models/` and can be authored in **SQL** or **Python**.

### SQL models

Create a `.sql` file anywhere inside your `models/` directory:

```sql
-- models/active_customers.sql
SELECT
  id,
  email,
  created_at
FROM raw.customers
WHERE is_deleted = false
```

KelpMesh parses the SQL AST to auto-detect dependencies — you don't need to declare them manually. If `active_customers.sql` references `stg_customers`, KelpMesh will build `stg_customers` first.

### Python models

For logic that is easier to express in code (API calls, complex joins, window functions), use a `.py` file:

```python
# models/active_customers.py
def model(dbt, session):
    customers = dbt.ref("stg_customers")
    df = session.execute_df(f"""
        SELECT id, email, created_at
        FROM {customers}
        WHERE is_deleted = false
    """)
    # Perform Python-side transformations
    df["domain"] = df["email"].str.split("@").str[1]
    return df
```

**Conventions:**
- The file must expose a `model(dbt, session)` function
- `dbt.ref("model_name")` resolves to the upstream model's fully-qualified table name
- `dbt.source("source_name", "table_name")` resolves a source table name
- `session.execute(sql)` runs raw SQL, returns `list[dict]`
- `session.execute_df(sql)` runs SQL and returns a `pandas.DataFrame`
- Return a **pandas DataFrame** or a **SQL string**; KelpMesh materializes the result

Python models default to `materialized="table"` (unlike SQL models which default to `"view"`). Override with a config comment at the top:

```python
# config: materialized="incremental", unique_key="id"
def model(dbt, session):
    ...
```

Run them the same way as SQL models:

```bash
kelpmesh run --select active_customers
```

---

## Materialization types

Configure how a model is persisted using a config block at the top of the file.

### view (default)

```sql
-- {{ config(materialized="view") }}
SELECT * FROM raw.orders
```

Creates a virtual view. No data is copied — the query executes at read time. Best for lightweight transformations on small or frequently-changing data.

### table

```sql
-- {{ config(materialized="table") }}
SELECT
  customer_id,
  SUM(amount) AS total_spent
FROM orders
GROUP BY customer_id
```

Drops and recreates the table on every `kelpmesh run`. Best for aggregated models where a full refresh is acceptable.

### incremental

```sql
-- {{ config(materialized="incremental", unique_key="order_id", incremental_strategy="merge") }}
SELECT
  order_id,
  customer_id,
  amount,
  status,
  updated_at
FROM raw.orders
WHERE updated_at > '{{ var("last_run") }}'
```

On the first run, creates the table from scratch. On subsequent runs, KelpMesh only processes new or updated rows without rebuilding the entire table. This is the most efficient strategy for large, append-only or slowly-changing datasets.

See [Incremental models](./incremental.md) for a full guide.

### ephemeral

```sql
-- {{ config(materialized="ephemeral") }}
SELECT id, LOWER(email) AS email FROM raw.users
```

Not materialized at all — inlined as a CTE wherever it is referenced. Zero warehouse objects created. Best for simple transformations reused across models.

---

## Configuration reference

Config blocks appear as SQL comments at the top of the file:

```sql
-- {{ config(
--     materialized="incremental",
--     unique_key="id",
--     incremental_strategy="merge",
--     tags=["daily", "finance"]
-- ) }}
```

| Key | Values | Default | Description |
|---|---|---|---|
| `materialized` | `view`, `table`, `incremental`, `ephemeral` | `view` | How the model is persisted |
| `unique_key` | column name | — | Required for `incremental` merge strategy |
| `incremental_strategy` | `append`, `merge` | `append` | `merge` upserts; `append` inserts only |
| `tags` | list of strings | `[]` | Labels for selective runs (`kelpmesh run --tag finance`) |
| `enabled` | `true`, `false` | `true` | Set `false` to skip a model without deleting it |

---

## Selecting models to run

```bash
# Run all models
kelpmesh run

# Run a single model
kelpmesh run --select orders_daily

# Run all models with a tag
kelpmesh run --tag finance

# Run a model and all its upstream dependencies
kelpmesh run --select +orders_daily

# Run a model and all its downstream dependents
kelpmesh run --select orders_daily+
```

---

## Project structure

```
my_project/
├── kelpmesh.yml            # Warehouse connection + project settings
├── models/
│   ├── staging/        # Raw → cleaned (views)
│   │   ├── stg_orders.sql
│   │   └── stg_customers.sql
│   ├── marts/          # Business-ready tables
│   │   ├── orders_daily.sql
│   │   └── customer_lifetime_value.sql
│   └── metrics.yml     # Semantic layer definitions
├── tests/              # Data quality assertions
├── seeds/              # Static reference data (CSV → table)
└── target/             # Compiled SQL + run artefacts (git-ignored)
```

---

## Schema YAML

Define metadata alongside your models in a `schema.yml` file:

```yaml
models:
  - name: orders_daily
    description: "Daily order aggregates by customer"
    access: public          # public | protected | private (for KelpMesh Mesh)
    columns:
      - name: customer_id
        description: "Foreign key to customers"
        tests:
          - not_null
          - unique
      - name: total_spent
        description: "Sum of all order amounts"
        tests:
          - not_null
```

---

## Variables

Pass variables at run time:

```bash
kelpmesh run --var "last_run=2025-01-01"
```

Reference them in SQL:

```sql
WHERE updated_at > '{{ var("last_run") }}'
```

Set defaults in `kelpmesh.yml`:

```yaml
vars:
  last_run: "1970-01-01"
```

---

## Legacy Jinja macros

KelpMesh is designed around **pure SQL** — no Jinja required. However, if you are migrating from dbt or have existing Jinja `{% macro %}` definitions, KelpMesh supports them as a compatibility layer.

Place Jinja macro files in `macros/*.sql`:

```sql
-- macros/my_macros.sql
{% macro mask_email(email) %}
    CONCAT(LEFT({{ email }}, 1), '****@', SUBSTRING({{ email }}, POSITION('@' IN {{ email }}) + 1))
{% endmacro %}
```

When `macros/*.sql` files contain `{% %}` blocks, KelpMesh automatically:

  - Detects them on project load via `MacroLoader`
  - Delegates the entire SQL rendering to a Sandboxed Jinja2 environment
  - Provides `var()`, `env_var()`, `is_incremental()`, and `this` as Jinja globals

The built-in `var()`, `env_var()`, `is_incremental()`, `this`, and 32 SQL-native macros (`surrogate_key`, `safe_divide`, etc.) work identically whether or not Jinja is enabled — they are available as plain function calls in both paths.

> **Note:** Jinja is a legacy fallback. The non-Jinja (regex-based) engine is faster, more predictable, and works with all SQL linters, formatters, and AI tools. For new projects, prefer the Jinja-free approach shown throughout this guide.
