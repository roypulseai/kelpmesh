# Model Materializations

Materializations control how KelpMesh writes model results to your warehouse. Declare them in the model file header or `schema.yml`.

## Declare in model header

```sql
-- materialized: table
-- unique_key: order_id
-- incremental_strategy: merge

SELECT ...
```

## Declare in schema.yml

```yaml
models:
  - name: orders_daily
    config:
      materialized: incremental
      unique_key: order_id
      incremental_strategy: merge
```

---

## view

Creates a SQL view. No data is stored — the query runs every time you query the view.

```sql
-- materialized: view

SELECT customer_id, SUM(amount) AS total_spend
FROM orders
GROUP BY 1
```

**When to use:** Lightweight models, real-time data, rarely queried.

**Warehouse support:** All warehouses.

---

## table

Drops and recreates the table on every run. Fast for medium datasets.

```sql
-- materialized: table

SELECT * FROM stg_orders WHERE status = 'completed'
```

**When to use:** Small-to-medium datasets, aggregations, no incremental logic needed.

---

## incremental

Appends or merges only new/changed rows. Checks `is_incremental()` to filter.

```sql
-- materialized: incremental
-- unique_key: order_id
-- incremental_strategy: merge

SELECT id AS order_id, customer_id, amount, updated_at
FROM raw_orders
{% if is_incremental() %}
WHERE updated_at > (SELECT MAX(updated_at) FROM {{ this }})
{% endif %}
```

**Strategies:**
- `append` (default) — `INSERT INTO`, no deduplication
- `merge` — `MERGE INTO` / `INSERT ... ON CONFLICT`, requires `unique_key`

**When to use:** Large tables where a full rebuild would be too slow.

---

## incremental_by_time_range

KelpMesh's interval-aware incremental. Tracks which date intervals have been computed and automatically backfills missing ones.

```sql
-- materialized: incremental_by_time_range
-- time_column: event_date
-- time_grain: day

SELECT
    event_date,
    user_id,
    COUNT(*) AS events
FROM raw_events
WHERE event_date >= '{{ var("start_date") }}'
  AND event_date <  '{{ var("end_date") }}'
GROUP BY 1, 2
```

KelpMesh tracks which `(start_date, end_date)` pairs have been run in the state DB. On each run it detects missing intervals and fills them in order.

**Backfill a date range:**
```bash
kelpmesh run --var start_date=2024-01-01 --var end_date=2024-12-31
```

**Check interval status:**
```bash
kelpmesh history --model user_events_daily
```

**time_grain options:** `day` (default), `week`, `month`, `hour`

---

## ephemeral

Compiled as a CTE inlined into the downstream model. Never materialized in the warehouse.

```sql
-- materialized: ephemeral

SELECT id, LOWER(email) AS email FROM raw_users
```

**When to use:** Lightweight transformations reused by a single downstream model.

---

## snapshot (SCD Type 2)

Tracks historical changes to a source table row-by-row.

```sql
-- materialized: snapshot
-- unique_key: customer_id
-- snapshot_strategy: timestamp
-- snapshot_updated_at: updated_at

SELECT customer_id, name, email, plan, updated_at
FROM raw_customers
```

Adds columns: `_scd_id`, `_valid_from`, `_valid_to`, `_is_current`, `_dbt_updated_at`.

**Strategies:** `timestamp` (compare `updated_at`) or `check` (hash all columns).

---

## materialized_view

A database-native materialized view. Persists the query result and can be refreshed.

```sql
-- materialized: materialized_view

SELECT product_id, SUM(revenue) AS total_revenue
FROM orders
GROUP BY 1
```

**Warehouse support:**

| Warehouse | Native MV | Fallback |
|-----------|-----------|---------|
| PostgreSQL | ✅ `CREATE MATERIALIZED VIEW` | — |
| Redshift | ✅ | — |
| Snowflake | ✅ Dynamic Tables | — |
| BigQuery | ✅ | — |
| Databricks | ✅ | — |
| DuckDB | ❌ | Falls back to `table` |
| MySQL | ❌ | Falls back to `table` |
| ClickHouse | ✅ (via `MATERIALIZED VIEW` engine) | — |

---

## Python models

A `.py` file that returns a DataFrame or DuckDB relation.

```python
# materialized: table

def model(ref, session):
    orders = ref("stg_orders")
    customers = ref("stg_customers")
    return orders.join(customers, "customer_id")
```

Place in your `models/` directory with a `.py` extension. Works with pandas DataFrames, DuckDB relations, and Spark DataFrames.
