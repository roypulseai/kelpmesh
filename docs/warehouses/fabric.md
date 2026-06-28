# Microsoft Fabric

KelpMesh supports Microsoft Fabric via the SQL Analytics endpoint (T-SQL over ODBC).

## Configuration

```yaml
warehouse:
  type: fabric
  account: myworkspace.datawarehouse.fabric.microsoft.com
  database: MyLakehouse
  threads: 4
```

Or use a direct connection string:

```yaml
warehouse:
  type: fabric
  connection_string: "Driver={ODBC Driver 18 for SQL Server};Server=tcp:myworkspace.datawarehouse.fabric.microsoft.com,1433;Database=MyLakehouse;Encrypt=yes;"
```

## Install dependencies

```bash
pip install pyodbc azure-identity
```

Install the **ODBC Driver 18 for SQL Server**:

- **Windows**: [Download from Microsoft](https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- **macOS**: `brew install microsoft/mssql-release/msodbcsql18`
- **Linux**: [Microsoft Linux instructions](https://docs.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server)

## Authentication

The Fabric adapter uses `DefaultAzureCredential` from `azure-identity`. It tries sources in order:

1. Environment variables (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`)
2. Azure CLI (`az login`)
3. Managed Identity (when running in Azure)
4. Visual Studio / VS Code credentials

For local development, `az login` is the simplest option.

## Permissions

```sql
GRANT CREATE TABLE TO [your_principal];
GRANT CREATE VIEW TO [your_principal];
GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::dbo TO [your_principal];
```

## Materialization support

| Materialization | Supported | Notes |
|---|---|---|
| `view` | ✅ | `CREATE VIEW` (T-SQL) |
| `table` | ✅ | `SELECT * INTO` (T-SQL — not `CREATE TABLE AS`) |
| `incremental` (append) | ✅ | `INSERT INTO` |
| `incremental` (merge) | ✅ | T-SQL `MERGE INTO` |
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
WHERE updated_at >= DATEADD(DAY, -7, GETDATE())
```

KelpMesh generates a T-SQL MERGE:

```sql
MERGE INTO [dim_customers] AS target
USING (...) AS source
ON target.[customer_id] = source.[customer_id]
WHEN MATCHED THEN UPDATE SET target.[email] = source.[email], ...
WHEN NOT MATCHED THEN INSERT ([customer_id], [email], ...) VALUES (source.[customer_id], ...);
```

Note the trailing semicolon — required by T-SQL MERGE syntax.

## T-SQL differences

| Standard SQL | T-SQL equivalent |
|---|---|
| `CREATE TABLE t AS SELECT ...` | `SELECT * INTO t FROM (...) AS _src` |
| `LIMIT n` | `SELECT TOP n` |
| `CREATE OR REPLACE VIEW` | `ALTER VIEW` / `CREATE VIEW` |
| `NOW()` | `GETDATE()` |
| `INTERVAL '7' DAY` | `DATEADD(DAY, 7, date)` |

KelpMesh handles the `CREATE TABLE` difference automatically.
