# PostgreSQL

## Configuration

```yaml
warehouse:
  type: postgres
  host: localhost
  port: 5432
  database: analytics
  user: briq_user
  password: "{{ env_var('POSTGRES_PASSWORD') }}"
  schema: public       # optional, defaults to public
  threads: 4
```

## Install dependencies

```bash
pip install psycopg2-binary
```

## User permissions

```sql
CREATE USER briq_user WITH PASSWORD 'your_password';
GRANT USAGE ON SCHEMA public TO briq_user;
GRANT CREATE ON SCHEMA public TO briq_user;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO briq_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT SELECT ON TABLES TO briq_user;
```

## Materialization support

| Materialization | Supported | Notes |
|---|---|---|
| `view` | ✅ | `CREATE OR REPLACE VIEW` |
| `table` | ✅ | `CREATE TABLE AS SELECT` |
| `incremental` (append) | ✅ | `INSERT INTO` |
| `incremental` (merge) | ✅ | `INSERT ... ON CONFLICT DO UPDATE` (PG 9.5+) |
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

KelpMesh uses PostgreSQL's `INSERT ... ON CONFLICT DO UPDATE` pattern:

```sql
INSERT INTO dim_customers ("customer_id", "email", ...)
SELECT "customer_id", "email", ... FROM _briq_merge_dim_customers
ON CONFLICT ("customer_id") DO UPDATE SET "email" = EXCLUDED."email", ...
```

> Requires PostgreSQL 9.5 or later. The target column must have a UNIQUE constraint or be a PRIMARY KEY
> for `ON CONFLICT` to work. KelpMesh does not create constraints automatically — add them with:
> ```sql
> ALTER TABLE dim_customers ADD CONSTRAINT dim_customers_pkey PRIMARY KEY (customer_id);
> ```

## SSL

To require SSL (recommended for production):

```yaml
warehouse:
  type: postgres
  host: db.example.com
  port: 5432
  database: analytics
  user: briq_user
  password: "{{ env_var('POSTGRES_PASSWORD') }}"
```

Postgres defaults to `sslmode=prefer`. For stricter enforcement, pass via `connection_string`:

```yaml
warehouse:
  type: postgres
  connection_string: "postgresql://briq_user:pass@db.example.com:5432/analytics?sslmode=require"
```
