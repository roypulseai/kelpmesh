# System Requirements

## Python

KelpMesh requires **Python 3.11 or later**.

| Python | Status |
|--------|--------|
| 3.13   | ✅ Supported |
| 3.12   | ✅ Supported |
| 3.11   | ✅ Supported |
| 3.10   | ❌ Not supported (no `match/case` with guards) |
| < 3.10 | ❌ Not supported |

## Operating System

| OS | Status |
|----|--------|
| Windows 11 / Windows Server 2022+ | ✅ Supported |
| Ubuntu 20.04 LTS / Debian 11+ | ✅ Supported |
| macOS 12 Monterey+ | ✅ Supported |
| Other Linux (RHEL 8+, Alpine) | ✅ Generally works |

## Hardware

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 512 MB | 2 GB+ |
| Disk | 200 MB (core + DuckDB) | 2 GB+ (for large state DBs) |
| CPU | Any | 2+ cores (for `--threads 4`) |

## Core Dependencies (auto-installed)

KelpMesh-core has intentionally minimal dependencies — all installed automatically via pip:

```
typer>=0.12       CLI framework
sqlglot>=25.0     SQL parsing, linting, transpilation
networkx>=3.0     DAG / dependency graph
duckdb>=1.0       State engine + local warehouse
pydantic>=2.0     Config validation
rich>=13.0        Terminal output
jinja2>=3.0       Template compatibility layer
pyyaml>=6.0       Config files
sqlparse>=0.5     SQL formatting
cryptography>=42  State encryption
```

## Warehouse Driver Extras

Install only what you need:

```bash
# Local / DuckDB (no extra needed — built-in)
pip install kelpmesh-core

# PostgreSQL / Amazon Redshift
pip install "kelpmesh-core[postgres]"

# Snowflake
pip install "kelpmesh-core[snowflake]"

# Google BigQuery
pip install "kelpmesh-core[bigquery]"

# Databricks
pip install "kelpmesh-core[databricks]"

# Microsoft Fabric (requires pyodbc + Azure SDK)
pip install "kelpmesh-core[fabric]"

# MySQL / MariaDB
pip install "kelpmesh-core[mysql]"

# ClickHouse
pip install "kelpmesh-core[clickhouse]"

# Trino / Presto
pip install "kelpmesh-core[trino]"

# Apache Spark
pip install "kelpmesh-core[spark]"

# Amazon Athena
pip install "kelpmesh-core[athena]"

# Apache Hive
pip install "kelpmesh-core[hive]"

# SQL Server / Azure Synapse  (also requires OS-level ODBC driver)
pip install "kelpmesh-core[sqlserver]"

# All major warehouses at once
pip install "kelpmesh-core[all-warehouses]"
```

### OS-Level Driver Requirements

Some adapters require an OS-level driver beyond the Python package:

**SQL Server / Azure Synapse — ODBC Driver 18**
```bash
# Windows: download from https://aka.ms/odbc18
# Ubuntu/Debian:
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
sudo apt install msodbcsql18
# macOS:
brew install msodbcsql18
```

**Microsoft Fabric — pyodbc**
```bash
# Same ODBC driver as SQL Server above
```

**Apache Hive — SASL/Kerberos (optional)**
```bash
# Ubuntu/Debian (for Kerberos-secured HiveServer2):
sudo apt install libsasl2-dev libkrb5-dev
pip install "kelpmesh-core[hive]"
```

## Optional Integrations

| Integration | Package | Min Version |
|-------------|---------|-------------|
| Apache Airflow | `apache-airflow` | 2.8 |
| Dagster | `dagster dagster-webserver` | 1.6 |
| Prefect | `prefect` | 3.0 |
| MkDocs (for docs site) | `mkdocs mkdocs-material` | 1.6 / 9.5 |

Install a specific orchestrator:
```bash
pip install "kelpmesh-core[dagster]"
pip install "kelpmesh-core[airflow]"
pip install "kelpmesh-core[prefect]"
```

## kelpmesh-studio Additional Requirements

KelpMesh Studio adds a web UI on top of the core:

```bash
pip install kelpmesh-studio
```

Studio requires:
- All requirements above
- A browser (Chrome 120+, Firefox 122+, Safari 17+, Edge 120+)
- Port 8501 available (configurable)

## Network Requirements

KelpMesh-core itself makes **zero outbound network calls**. All communication is with your own warehouse.

KelpMesh Studio telemetry is also **disabled by default** and can be verified at startup with `kelpmesh debug`.

## Verify Installation

```bash
# Check Python version
python --version

# Verify kelpmesh installed correctly
kelpmesh --version

# Check connection to your warehouse
kelpmesh debug

# Run self-test (no warehouse needed — uses in-memory DuckDB)
kelpmesh run --project-dir examples/quickstart
```
