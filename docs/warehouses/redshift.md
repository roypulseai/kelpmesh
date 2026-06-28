# Amazon Redshift

## Configuration

```yaml
warehouse:
  type: redshift
  host: my-cluster.abc123.us-east-1.redshift.amazonaws.com
  port: 5439          # default Redshift port
  database: analytics
  user: briq_user
  password: "{{ env_var('REDSHIFT_PASSWORD') }}"
```

## Install dependencies

```bash
pip install psycopg2-binary
```

Redshift uses the PostgreSQL wire protocol, so `psycopg2` is the only dependency needed.

## IAM authentication (recommended)

For production, use IAM database authentication instead of a password:

1. Enable IAM auth on your Redshift cluster.
2. Create an IAM role with `redshift:GetClusterCredentials` permission.
3. Use a short-lived token (15 minutes) as the password:

```bash
export REDSHIFT_PASSWORD=$(aws redshift get-cluster-credentials \
  --cluster-identifier my-cluster \
  --db-user briq_user \
  --db-name analytics \
  --query DbPassword \
  --output text)
```

```yaml
warehouse:
  type: redshift
  host: my-cluster.abc123.us-east-1.redshift.amazonaws.com
  port: 5439
  database: analytics
  user: briq_user
  password: "{{ env_var('REDSHIFT_PASSWORD') }}"
```

## User permissions

Grant your briq user the permissions it needs:

```sql
-- Grant schema access
GRANT USAGE ON SCHEMA public TO briq_user;

-- Grant table creation (needed for materializations)
GRANT CREATE ON SCHEMA public TO briq_user;

-- Grant read access to source schemas
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO briq_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT SELECT ON TABLES TO briq_user;
```

## Materialization support

| Materialization | Supported | Notes |
|---|---|---|
| `view` | ✅ | `CREATE OR REPLACE VIEW` |
| `table` | ✅ | `CREATE TABLE AS SELECT` |
| `incremental` (append) | ✅ | `INSERT INTO` |
| `incremental` (merge) | ✅ | Redshift `MERGE` (2022+) |
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
WHERE updated_at >= CURRENT_DATE - 7
```

briq uses Redshift's native `MERGE` statement:

```sql
MERGE INTO dim_customers
USING (...) AS source
ON dim_customers."customer_id" = source."customer_id"
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT (...) VALUES (...)
```

> Redshift MERGE requires Redshift engine version 1.0.40325 or later (released 2022).
> On older clusters, use `incremental_strategy: "append"` and manage deduplication manually.

## Performance tips

- **Sort keys**: Add `SORTKEY` and `DISTKEY` to frequently-joined tables. briq creates tables with no distribution by default; use raw SQL `CREATE TABLE ... SORTKEY(col)` for large tables.
- **Vacuum and analyze**: Run `VACUUM; ANALYZE;` after large loads to keep statistics current.
- **Concurrency scaling**: Enable concurrency scaling on your cluster for parallel `briq run` with `threads: 8`.
- **WLM queues**: Create a dedicated WLM queue for briq transforms and set a queue priority to avoid competing with BI queries.

## Connection pooling

Redshift supports a limited number of concurrent connections per cluster. Set `threads` conservatively:

```yaml
warehouse:
  type: redshift
  threads: 4   # safe default; max ~50 per cluster depending on node type
  ...
```
