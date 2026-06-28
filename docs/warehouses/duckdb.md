# DuckDB

The default warehouse for briq. No external dependencies, no server, no credentials — runs entirely in-process. Ideal for local development, CI pipelines, and analytics on files.

## Configuration

```yaml
warehouse:
  type: duckdb
  database: ./target/dev.duckdb   # path to .duckdb file; omit for in-memory
  threads: 4
```

Omit `database` for a pure in-memory database:

```yaml
warehouse:
  type: duckdb
```

## Features

- Zero-configuration — no server, no credentials
- File-based or in-memory
- Transparent encryption via `BRIQ_ENCRYPTION_KEY`
- Thread-safe connection pooling for parallel model execution

## Materialization support

| Materialization | Supported | Notes |
|---|---|---|
| `view` | ✅ | `CREATE OR REPLACE VIEW` |
| `table` | ✅ | `CREATE TABLE AS SELECT` |
| `incremental` (append) | ✅ | `INSERT INTO` |
| `incremental` (merge) | ✅ | `INSERT ... ON CONFLICT DO UPDATE` |
| `ephemeral` | ✅ | Inlined as CTE |
| Snapshot (SCD Type 2) | ✅ | `briq snapshot` command |

### Incremental merge example

```sql
-- {{ config(materialized="incremental", unique_key="customer_id", incremental_strategy="merge") }}
SELECT
  customer_id,
  email,
  plan,
  updated_at
FROM raw.customers
WHERE updated_at >= CURRENT_DATE - INTERVAL 7 DAYS
```

### Reading files directly

DuckDB can query CSV, Parquet, and JSON files without loading them first:

```sql
-- models/raw_orders.sql
SELECT * FROM read_csv_auto('./data/orders_*.csv')

-- models/raw_events.sql
SELECT * FROM read_parquet('./data/events/2025/**/*.parquet')
```

## SCD Type 2 snapshots

```bash
briq snapshot --select dim_customers --strategy timestamp --unique-key customer_id
```

Adds four system columns to the target table:

| Column | Description |
|---|---|
| `_valid_from` | When this row version became active |
| `_valid_to` | When it was superseded (NULL = currently active) |
| `_is_current` | Convenience flag for the latest version |
| `_scd_id` | Unique hash for this row version |

## Dev + prod with different warehouses

Develop locally with DuckDB, deploy to Snowflake or BigQuery in production:

```yaml
# briq.yml
warehouse:
  type: "{{ env_var('BRIQ_WAREHOUSE', 'duckdb') }}"
  database: ./target/dev.duckdb
```

```bash
# Local
briq run

# Production
BRIQ_WAREHOUSE=snowflake briq run
```
