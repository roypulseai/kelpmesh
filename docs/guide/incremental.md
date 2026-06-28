# Incremental models

Incremental models let you process only the rows that are new or changed since the last run, rather than rebuilding the entire table from scratch. This is the single most important performance optimization for large datasets.

---

## How it works

1. **First run** — briq runs your full `SELECT` and creates the table.
2. **Subsequent runs** — briq runs the same `SELECT` (filtered by your incremental logic) and either appends or merges the results into the existing table.

---

## Strategies

### append

Inserts new rows. Never updates existing rows. Use for immutable event streams (logs, clickstream, raw API responses).

```sql
-- {{ config(materialized="incremental", incremental_strategy="append") }}

SELECT
  event_id,
  user_id,
  event_type,
  occurred_at
FROM raw.events
WHERE occurred_at >= CURRENT_DATE - INTERVAL '1 day'
```

### merge

Upserts rows: updates matching rows (by `unique_key`) and inserts new ones. Use for dimension tables, slowly-changing datasets, or any source where rows can be edited.

```sql
-- {{ config(materialized="incremental", unique_key="customer_id", incremental_strategy="merge") }}

SELECT
  customer_id,
  email,
  plan,
  updated_at
FROM raw.customers
WHERE updated_at >= CURRENT_DATE - INTERVAL '7 days'
```

---

## Filtering incremental runs

The most common pattern is to filter by a timestamp column. You can use `briq run --var` to pass the high-watermark, or store it externally and inject it at run time.

**Recommended pattern:**

```sql
-- {{ config(materialized="incremental", unique_key="id", incremental_strategy="merge") }}

SELECT id, name, status, updated_at
FROM raw.records
{% if is_incremental() %}
  WHERE updated_at > (SELECT MAX(updated_at) FROM {{ this }})
{% endif %}
```

> `{{ this }}` refers to the current model's table. `is_incremental()` returns `true` when the table already exists and the run is not a full refresh.

**Note:** briq does not yet parse Jinja — use `--var` or an external scheduler to pass the watermark for now. Full Jinja support is on the roadmap.

---

## Full refresh

Force a full rebuild of an incremental model:

```bash
briq run --select orders --full-refresh
```

This drops and recreates the table, regardless of incremental strategy.

---

## Warehouse support matrix

| Warehouse | append | merge | Notes |
|---|---|---|---|
| **DuckDB** | ✅ | ✅ | `INSERT ... ON CONFLICT DO UPDATE` |
| **PostgreSQL** | ✅ | ✅ | `INSERT ... ON CONFLICT DO UPDATE` (requires PG 9.5+) |
| **Redshift** | ✅ | ✅ | `MERGE` statement (requires Redshift 2022+) |
| **Snowflake** | ✅ | ✅ | `MERGE INTO ... USING` |
| **BigQuery** | ✅ | ✅ | `MERGE` statement |
| **Databricks** | ✅ | ✅ | Delta Lake `MERGE INTO` with `UPDATE SET *` |
| **Microsoft Fabric** | ✅ | ✅ | T-SQL `MERGE INTO` |

---

## SCD Type 2 (slowly-changing dimensions)

briq supports Slowly Changing Dimensions (Type 2) natively on DuckDB, with other warehouses on the roadmap.

```python
# In Python via the briq SDK
adapter.execute_snapshot(
    sql="SELECT id, name, email FROM raw.customers",
    table_name="dim_customers",
    unique_key="id",
    strategy="timestamp",          # or "check"
    updated_at_col="updated_at",   # for timestamp strategy
    check_cols=["email", "plan"],  # for check strategy
)
```

SCD Type 2 adds four system columns to the target table:

| Column | Type | Description |
|---|---|---|
| `_valid_from` | timestamp | When this version became active |
| `_valid_to` | timestamp | When this version was superseded (NULL = current) |
| `_is_current` | boolean | Convenience flag for the latest version |
| `_scd_id` | varchar | Unique hash for this row version |

---

## Best practices

- **Always set `unique_key`** when using the merge strategy. Without it, briq falls back to append.
- **Filter your incremental query** — without a filter, every run processes the full source table even if only new rows are materialized.
- **Use `MAX(updated_at)` from `{{ this }}`** rather than a fixed date so the watermark advances automatically.
- **Test your incremental logic** with a short date range before running it on years of data.
- **Schedule with `--full-refresh` weekly** for merge models to correct any data quality issues that slipped through.
