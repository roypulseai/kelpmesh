# Microsoft Fabric

briq supports Microsoft Fabric via the SQL Analytics endpoint (T-SQL over ODBC).

## Configuration

```yaml
# briq.yml
warehouse:
  type: fabric
  account: myworkspace-abc123.datawarehouse.fabric.microsoft.com
  database: my_warehouse
```

Or use a direct connection string:

```yaml
warehouse:
  type: fabric
  connection_string: "Driver={ODBC Driver 18 for SQL Server};Server=tcp:...,1433;Database=...;Encrypt=yes;"
```

## Authentication

The Fabric adapter uses `DefaultAzureCredential` from the `azure-identity` package. It works with:

- Azure CLI login (`az login`)
- Managed identities
- Service principals (via environment variables)
- Visual Studio / VS Code Azure Account extension

## Required ODBC Driver

Install the [Microsoft ODBC Driver for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server).

## Install dependencies

```bash
pip install pyodbc azure-identity
```
