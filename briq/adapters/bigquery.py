import logging
from briq.adapters.base import WarehouseAdapter, sanitize_name
from briq.core.config import WarehouseConfig

_logger = logging.getLogger(__name__)


class BigQueryAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig):
        self.config = config
        self.client = None

    def connect(self):
        from google.cloud import bigquery
        if self.config.private_key_path:
            self.client = bigquery.Client.from_service_account_json(
                self.config.private_key_path
            )
        else:
            self.client = bigquery.Client(project=self.config.project_id)

    def disconnect(self):
        self.client = None

    def execute(self, sql: str, conn=None) -> list[dict]:
        if not self.client:
            self.connect()
        job = self.client.query(sql)
        rows = job.result()
        return [dict(row.items()) for row in rows]

    def execute_model(
        self, sql: str, table_name: str, materialized: str = "view",
        conn=None, unique_key: str | None = None,
        incremental_strategy: str = "append",
    ):
        safe = sanitize_name(table_name)
        self.drop_table(table_name, materialized)
        dataset = self.config.database or self.client.project
        full_name = f"{dataset}.{safe}"
        if not self.client:
            self.connect()
        if materialized == "table":
            self.client.query(f"CREATE TABLE {full_name} AS {sql}").result()
        else:
            self.client.query(f"CREATE OR REPLACE VIEW {full_name} AS {sql}").result()

    def table_exists(self, table_name: str, conn=None) -> bool:
        if not self.client:
            return False
        dataset = self.config.database or self.client.project
        try:
            self.client.get_table(f"{dataset}.{table_name}")
            return True
        except Exception as e:
            _logger.debug("table_exists check failed for %s: %s", table_name, e)
            return False

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        if not self.client:
            return []
        dataset = self.config.database or self.client.project
        table = self.client.get_table(f"{dataset}.{table_name}")
        return [{"column_name": s.name, "data_type": s.field_type} for s in table.schema]

    def drop_table(self, table_name: str, materialized: str = "view", conn=None):
        safe = sanitize_name(table_name)
        if not self.client:
            return
        dataset = self.config.database or self.client.project
        full_name = f"{dataset}.{safe}"
        kind = "VIEW" if materialized == "view" else "TABLE"
        self.client.query(f"DROP {kind} IF EXISTS {full_name}").result()
