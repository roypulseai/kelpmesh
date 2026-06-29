"""kelpmesh adapters — Database/warehouse connector implementations."""

from kelpmesh.adapters.base import WarehouseAdapter
from kelpmesh.core.config import WarehouseConfig


def get_adapter(config: WarehouseConfig, project_path: str | None = None) -> WarehouseAdapter:
    match config.type:
        case "duckdb":
            from kelpmesh.adapters.duckdb import DuckDBAdapter
            return DuckDBAdapter(config, project_path=project_path)
        case "snowflake":
            from kelpmesh.adapters.snowflake import SnowflakeAdapter
            return SnowflakeAdapter(config)
        case "bigquery":
            from kelpmesh.adapters.bigquery import BigQueryAdapter
            return BigQueryAdapter(config)
        case "postgres":
            from kelpmesh.adapters.postgres import PostgresAdapter
            return PostgresAdapter(config)
        case "redshift":
            from kelpmesh.adapters.redshift import RedshiftAdapter
            return RedshiftAdapter(config)
        case "databricks":
            from kelpmesh.adapters.databricks import DatabricksAdapter
            return DatabricksAdapter(config)
        case "fabric":
            from kelpmesh.adapters.fabric import FabricAdapter
            return FabricAdapter(config)
        case "mysql" | "mariadb":
            from kelpmesh.adapters.mysql import MySQLAdapter
            return MySQLAdapter(config)
        case "trino" | "presto":
            from kelpmesh.adapters.trino import TrinoAdapter
            return TrinoAdapter(config)
        case "clickhouse":
            from kelpmesh.adapters.clickhouse import ClickHouseAdapter
            return ClickHouseAdapter(config)
        case "spark":
            from kelpmesh.adapters.spark import SparkAdapter
            return SparkAdapter(config)
        case "athena":
            from kelpmesh.adapters.athena import AthenaAdapter
            return AthenaAdapter(config)
        case "hive":
            from kelpmesh.adapters.hive import HiveAdapter
            return HiveAdapter(config)
        case "sqlserver" | "mssql" | "synapse" | "azuresynapse":
            from kelpmesh.adapters.sqlserver import SQLServerAdapter
            return SQLServerAdapter(config)
        case _:
            from kelpmesh.adapters.duckdb import DuckDBAdapter
            return DuckDBAdapter(config, project_path=project_path)


__all__ = [
    "WarehouseAdapter",
    "WarehouseConfig",
    "get_adapter",
]
