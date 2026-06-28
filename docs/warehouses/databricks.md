# Databricks

KelpMesh connects to Databricks via the Databricks SQL Connector and runs transforms on Delta Lake tables.

## Configuration

```yaml
warehouse:
  type: databricks
  account: adb-1234567890.12.azuredatabricks.net   # workspace hostname
  path: /sql/1.0/warehouses/abc123def456           # SQL warehouse HTTP path
  password: "{{ env_var('DATABRICKS_TOKEN') }}"    # personal access token
  database: my_catalog.my_schema                   # Unity Catalog or hive_metastore
  threads: 8
```

## Install dependencies

```bash
pip install databricks-sql-connector
```

## Get connection details

1. In your Databricks workspace, navigate to **SQL Warehouses**.
2. Select your warehouse → **Connection details**.
3. Copy the **Server hostname** (→ `account`) and **HTTP path** (→ `path`).

## Personal access token

```bash
databricks tokens create --comment "kelpmesh"
```

Or: **User Settings → Developer → Access tokens → Generate new token**.

## Unity Catalog

Set `database` to a fully-qualified `catalog.schema`:

```yaml
warehouse:
  type: databricks
  account: adb-1234567890.12.azuredatabricks.net
  path: /sql/1.0/warehouses/abc123
  password: "{{ env_var('DATABRICKS_TOKEN') }}"
  database: main.analytics
```

## Materialization support

| Materialization | Supported | Notes |
|---|---|---|
| `view` | ✅ | `CREATE OR REPLACE VIEW` |
| `table` | ✅ | `CREATE TABLE AS SELECT` (Delta) |
| `incremental` (append) | ✅ | `INSERT INTO` |
| `incremental` (merge) | ✅ | Delta Lake `MERGE INTO` with `UPDATE SET *` |
| `ephemeral` | ✅ | Inlined as CTE |

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

KelpMesh uses Delta Lake's native MERGE with wildcard column matching:

```sql
MERGE INTO dim_customers AS target
USING (...) AS source
ON target.`customer_id` = source.`customer_id`
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
```

`UPDATE SET *` and `INSERT *` automatically match all columns by name.

## Delta Lake features

All KelpMesh tables on Databricks are Delta tables, giving you:

- **Time travel**: `SELECT * FROM dim_customers VERSION AS OF 5`
- **OPTIMIZE + ZORDER**: `OPTIMIZE dim_customers ZORDER BY (customer_id)`
- **Auto-compaction**: `TBLPROPERTIES ('delta.autoOptimize.autoCompact' = 'true')`
- **Change Data Feed**: `TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')`

## Serverless SQL warehouses

Use a Serverless SQL warehouse for near-zero cold-start and automatic scaling — ideal for scheduled `kelpmesh run` jobs. Set the `path` to a serverless warehouse HTTP path and KelpMesh works identically.
