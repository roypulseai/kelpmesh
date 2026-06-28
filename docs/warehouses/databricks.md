# Databricks

## Configuration

```yaml
warehouse:
  type: databricks
  account: your-server.databricks.com
  path: /sql/1.0/warehouses/your-http-path
  password: your-access-token
  database: your_catalog
  schema: default
```

## Install dependencies

```bash
pip install databricks-sql-connector
```
