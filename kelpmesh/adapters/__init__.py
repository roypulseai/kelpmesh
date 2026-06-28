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
        case _:
            from kelpmesh.adapters.duckdb import DuckDBAdapter
            return DuckDBAdapter(config, project_path=project_path)
