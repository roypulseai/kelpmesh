# Grain & Audits

## grain:

`grain:` declares which column(s) uniquely identify each row in a model — the "primary key" of the model's output. After every run, KelpMesh verifies that no duplicate grain combinations exist.

### Declare in model header

```sql
-- materialized: table
-- grain: order_id

SELECT order_id, customer_id, amount FROM raw_orders
```

### Composite grain

```sql
-- materialized: table
-- grain: user_id, event_date

SELECT user_id, event_date, COUNT(*) AS events
FROM raw_events
GROUP BY 1, 2
```

### What happens on failure

If duplicate grain rows are found after the model runs:
```
Warning: Audit failed [orders.grain]: 3 duplicate grain combination(s) on [order_id]
```

This is a warning by default. To make it a hard failure, use an audit:

```sql
-- materialized: table
-- grain: order_id
-- audits: assert_no_duplicate_orders
```

---

## audits:

`audits:` lists named SQL files that must return **zero rows** after the model runs. If any rows are returned, the audit fails.

Audit files live in `audits/` or `tests/audits/` in your project.

### Declare audits

```sql
-- materialized: incremental
-- unique_key: order_id
-- audits: no_negative_amounts, no_future_dates
```

### Write audit SQL

`audits/no_negative_amounts.sql`:
```sql
-- This audit FAILS if any rows are returned
-- description: Orders must not have negative amounts
SELECT order_id, amount
FROM {table}
WHERE amount < 0
```

`audits/no_future_dates.sql`:
```sql
SELECT order_id, created_at
FROM {table}
WHERE created_at > CURRENT_DATE + INTERVAL '1 day'
```

The `{table}` placeholder is replaced with the actual table name at runtime.

### Audit search paths

KelpMesh looks for audit files in this order:
1. `<project>/audits/<audit_name>.sql`
2. `<project>/tests/audits/<audit_name>.sql`

### Audits vs Tests

| | Audits | Tests |
|--|--------|-------|
| **When run** | After each model run | `kelpmesh test` only |
| **Scope** | Single model output | Any SQL |
| **Location** | `audits/` | `tests/` |
| **Failure effect** | Warning (non-blocking by default) | Blocking (exit 1) |

Use **audits** for post-materialization data quality checks on a single model.
Use **tests** for cross-model integrity checks (referential integrity, freshness, etc.).

### grain: equivalent in schema.yml

You can also declare grain in `schema.yml` and it works as a uniqueness test:

```yaml
models:
  - name: orders_daily
    config:
      grain: [user_id, date]
```
