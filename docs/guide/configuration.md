# Configuration

## briq.yml

```yaml
name: my_project
models_path: models
tests_path: tests
target_path: target

warehouse:
  type: duckdb        # or: snowflake, bigquery, postgres, databricks, fabric
  database: my_db
  schema: main
  path: target/briq.duckdb
  threads: 4
```

### Warehouse-specific configs

=== "DuckDB"

    ```yaml
    warehouse:
      type: duckdb
      path: target/briq.duckdb
      encryption_key:  # optional, set via BRIQ_ENCRYPTION_KEY env var
    ```

=== "Snowflake"

    ```yaml
    warehouse:
      type: snowflake
      account: your_account
      user: your_user
      password: your_password
      database: your_db
      role: your_role
      warehouse: your_warehouse
      schema: public
    ```

=== "BigQuery"

    ```yaml
    warehouse:
      type: bigquery
      project_id: your_project
      private_key_path: /path/to/key.json  # optional
      database: your_dataset
    ```

=== "Postgres"

    ```yaml
    warehouse:
      type: postgres
      host: localhost
      port: 5432
      user: your_user
      password: your_password
      database: your_db
    ```

=== "Databricks"

    ```yaml
    warehouse:
      type: databricks
      account: your-server.databricks.com
      path: /sql/1.0/warehouses/your-http-path
      password: your-access-token
      database: your_catalog
      schema: default
    ```

=== "Microsoft Fabric"

    ```yaml
    warehouse:
      type: fabric
      account: workspace-abc.datawarehouse.fabric.microsoft.com
      database: your_warehouse
    ```
