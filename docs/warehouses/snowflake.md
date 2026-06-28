# Snowflake

## Configuration

```yaml
warehouse:
  type: snowflake
  account: myorg-myaccount     # e.g. xy12345.us-east-1
  user: BRIQ_USER
  password: "{{ env_var('SNOWFLAKE_PASSWORD') }}"
  role: TRANSFORMER             # optional
  warehouse: COMPUTE_WH         # Snowflake virtual warehouse
  database: ANALYTICS
  schema: PUBLIC                # optional
  threads: 8
```

## Install dependencies

```bash
pip install snowflake-connector-python
```

## Key pair authentication (recommended)

```yaml
warehouse:
  type: snowflake
  account: myorg-myaccount
  user: BRIQ_USER
  private_key_path: /path/to/rsa_key.p8
  role: TRANSFORMER
  warehouse: COMPUTE_WH
  database: ANALYTICS
```

Generate a key pair:

```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
```

Register the public key in Snowflake:

```sql
ALTER USER BRIQ_USER SET RSA_PUBLIC_KEY='MIIBIjANBgkq...';
```

## User permissions

```sql
CREATE ROLE BRIQ_ROLE;
GRANT ROLE BRIQ_ROLE TO USER BRIQ_USER;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE BRIQ_ROLE;
GRANT USAGE ON DATABASE ANALYTICS TO ROLE BRIQ_ROLE;
GRANT USAGE ON SCHEMA ANALYTICS.PUBLIC TO ROLE BRIQ_ROLE;
GRANT CREATE TABLE ON SCHEMA ANALYTICS.PUBLIC TO ROLE BRIQ_ROLE;
GRANT CREATE VIEW ON SCHEMA ANALYTICS.PUBLIC TO ROLE BRIQ_ROLE;
GRANT SELECT ON ALL TABLES IN SCHEMA RAW.PUBLIC TO ROLE BRIQ_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA RAW.PUBLIC TO ROLE BRIQ_ROLE;
```

## Materialization support

| Materialization | Supported | Notes |
|---|---|---|
| `view` | ✅ | `CREATE OR REPLACE VIEW` |
| `table` | ✅ | `CREATE TABLE AS SELECT` |
| `incremental` (append) | ✅ | `INSERT INTO` |
| `incremental` (merge) | ✅ | Snowflake `MERGE INTO ... USING` |
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

briq generates a Snowflake MERGE statement:

```sql
MERGE INTO dim_customers AS target
USING (...) AS source
ON target."customer_id" = source."customer_id"
WHEN MATCHED THEN UPDATE SET target."email" = source."email", ...
WHEN NOT MATCHED THEN INSERT ("customer_id", "email", ...) VALUES (source."customer_id", ...)
```

## Performance tips

- Set `threads: 8` or higher — Snowflake handles concurrency well.
- Use `AUTO_SUSPEND` on your virtual warehouse to pause it when briq runs finish.
- Tag your virtual warehouse with `briq` to separate compute costs from BI workloads.
