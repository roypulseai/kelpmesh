from briq.adapters.base import WarehouseAdapter
from briq.core.config import WarehouseConfig


def get_adapter(config: WarehouseConfig, project_path: str | None = None) -> WarehouseAdapter:
    match config.type:
        case "duckdb":
            from briq.adapters.duckdb import DuckDBAdapter
            return DuckDBAdapter(config, project_path=project_path)
        case "snowflake":
            from briq.adapters.snowflake import SnowflakeAdapter
            return SnowflakeAdapter(config)
        case "bigquery":
            from briq.adapters.bigquery import BigQueryAdapter
            return BigQueryAdapter(config)
        case "postgres":
            from briq.adapters.postgres import PostgresAdapter
            return PostgresAdapter(config)
        case "databricks":
            from briq.adapters.databricks import DatabricksAdapter
            return DatabricksAdapter(config)
        case "fabric":
            from briq.adapters.fabric import FabricAdapter
            return FabricAdapter(config)
        case _:
            from briq.adapters.duckdb import DuckDBAdapter
            return DuckDBAdapter(config, project_path=project_path)
