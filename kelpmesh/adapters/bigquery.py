import logging

from kelpmesh.adapters.base import WarehouseAdapter, sanitize_name
from kelpmesh.core.config import WarehouseConfig

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

    def _client(self):
        if not self.client:
            self.connect()
        return self.client

    def _full_name(self, table_name: str) -> str:
        safe = sanitize_name(table_name)
        dataset = self.config.database or self._client().project
        return f"`{dataset}`.`{safe}`"

    def execute(self, sql: str, conn=None) -> list[dict]:
        job = self._client().query(sql)
        rows = job.result()
        return [dict(row.items()) for row in rows]

    def execute_model(
        self, sql: str, table_name: str, materialized: str = "view",
        conn=None, unique_key: str | None = None,
        incremental_strategy: str = "append",
    ):
        full = self._full_name(table_name)

        if materialized == "incremental":
            if self.table_exists(table_name):
                if unique_key and incremental_strategy == "merge":
                    # Inspect column names via LIMIT 0
                    job = self._client().query(f"SELECT * FROM ({sql}) AS _km_src LIMIT 0")
                    job.result()
                    cols = [field.name for field in job.schema]
                    col_list = ", ".join(f"`{col}`" for col in cols)
                    update_set = ", ".join(
                        f"target.`{col}` = source.`{col}`"
                        for col in cols if col != unique_key
                    )
                    source_vals = ", ".join(f"source.`{col}`" for col in cols)
                    merge_sql = f"""
                        MERGE {full} AS target
                        USING ({sql}) AS source
                        ON target.`{unique_key}` = source.`{unique_key}`
                        WHEN MATCHED THEN UPDATE SET {update_set}
                        WHEN NOT MATCHED THEN INSERT ({col_list}) VALUES ({source_vals})
                    """
                    self._client().query(merge_sql).result()
                else:
                    self._client().query(f"INSERT INTO {full} {sql}").result()
            else:
                self._client().query(f"CREATE TABLE {full} AS {sql}").result()
            return

        self.drop_table(table_name, materialized)
        if materialized == "table":
            self._client().query(f"CREATE TABLE {full} AS {sql}").result()
        elif materialized == "ephemeral":
            pass
        else:
            dataset = self.config.database or self._client().project
            safe = sanitize_name(table_name)
            self._client().query(
                f"CREATE OR REPLACE VIEW `{dataset}`.`{safe}` AS {sql}"
            ).result()

    def table_exists(self, table_name: str, conn=None) -> bool:
        dataset = self.config.database or self._client().project
        try:
            self._client().get_table(f"{dataset}.{table_name}")
            return True
        except Exception as e:
            _logger.debug("table_exists check failed for %s: %s", table_name, e)
            return False

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        dataset = self.config.database or self._client().project
        table = self._client().get_table(f"{dataset}.{table_name}")
        return [{"column_name": s.name, "data_type": s.field_type} for s in table.schema]

    def drop_table(self, table_name: str, materialized: str = "view", conn=None):
        safe = sanitize_name(table_name)
        dataset = self.config.database or self._client().project
        full_name = f"{dataset}.{safe}"
        kind = "VIEW" if materialized == "view" else "TABLE"
        self._client().query(f"DROP {kind} IF EXISTS {full_name}").result()

    def execute_materialized_view(self, sql: str, table_name: str, conn=None) -> None:
        dataset = getattr(self.config, "warehouse_schema", None) or getattr(self.config, "schema", None) or "default"
        safe = table_name.replace("`", "")
        full_name = f"{self.config.project_id}.{dataset}.{safe}"
        client = self._client()
        client.query(f"DROP MATERIALIZED VIEW IF EXISTS `{full_name}`").result()
        client.query(f"CREATE MATERIALIZED VIEW `{full_name}` AS {sql}").result()

    def execute_snapshot(
        self,
        sql: str,
        table_name: str,
        unique_key: str,
        strategy: str = "timestamp",
        updated_at: str = "updated_at",
        conn=None,
    ) -> None:
        """SCD Type 2 snapshot execution."""
        client = self._client()
        dataset = self.config.database or client.project
        full_name = f"`{dataset}`.`{table_name}`"
        stage_name = f"_km_snap_stage_{table_name}"
        stage_full = f"`{dataset}`.`{stage_name}`"
        uk = unique_key

        try:
            if not self.table_exists(table_name):
                dbt_updated_expr = (
                    f'CAST(`{updated_at}` AS TIMESTAMP)'
                    if strategy == "timestamp"
                    else "CURRENT_TIMESTAMP()"
                )
                client.query(f"""
                    CREATE TABLE {full_name} AS
                    SELECT *,
                        TO_HEX(MD5(CAST(`{uk}` AS STRING))) AS _scd_id,
                        CURRENT_TIMESTAMP()                 AS _valid_from,
                        CAST(NULL AS TIMESTAMP)             AS _valid_to,
                        TRUE                                AS _is_current,
                        {dbt_updated_expr}                  AS _dbt_updated_at
                    FROM ({sql}) _src
                """).result()
                return

            # Stage incoming data
            client.query(f"DROP TABLE IF EXISTS {stage_full}").result()
            client.query(f"CREATE TABLE {stage_full} AS {sql}").result()

            if strategy == "timestamp":
                changed_cond = f'CAST(n.`{updated_at}` AS TIMESTAMP) > s._dbt_updated_at'
            else:
                job = client.query(f"SELECT * FROM {stage_full} LIMIT 0")
                job.result()
                cols = [field.name for field in job.schema]
                check_cols = [col for col in cols if col != uk]
                if check_cols:
                    changed_cond = " OR ".join(
                        f'n.`{col}` IS DISTINCT FROM s.`{col}`'
                        for col in check_cols
                    )
                else:
                    changed_cond = "FALSE"

            # Close changed records via MERGE
            client.query(f"""
                MERGE {full_name} s
                USING (
                    SELECT n.`{uk}`
                    FROM {stage_full} n
                    JOIN {full_name} s ON n.`{uk}` = s.`{uk}`
                    WHERE s._is_current = true AND ({changed_cond})
                ) changed
                ON s.`{uk}` = changed.`{uk}` AND s._is_current = true
                WHEN MATCHED THEN UPDATE SET
                    _valid_to = CURRENT_TIMESTAMP(),
                    _is_current = false
            """).result()

            dbt_updated_insert = (
                f'CAST(n.`{updated_at}` AS TIMESTAMP)'
                if strategy == "timestamp"
                else "CURRENT_TIMESTAMP()"
            )
            client.query(f"""
                INSERT INTO {full_name}
                SELECT n.*,
                    TO_HEX(MD5(CAST(n.`{uk}` AS STRING))) AS _scd_id,
                    CURRENT_TIMESTAMP()                   AS _valid_from,
                    CAST(NULL AS TIMESTAMP)               AS _valid_to,
                    TRUE                                  AS _is_current,
                    {dbt_updated_insert}                  AS _dbt_updated_at
                FROM {stage_full} n
                WHERE NOT EXISTS (
                    SELECT 1 FROM {full_name} s
                    WHERE s.`{uk}` = n.`{uk}` AND s._is_current = true
                )
            """).result()

            client.query(f"DROP TABLE IF EXISTS {stage_full}").result()
        except Exception:
            try:
                client.query(f"DROP TABLE IF EXISTS {stage_full}").result()
            except Exception:
                pass
            raise
