from kelpmesh.adapters.base import WarehouseAdapter, sanitize_name
from kelpmesh.core.config import WarehouseConfig


class DatabricksAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig):
        self.config = config
        self.conn = None

    def connect(self):
        try:
            from databricks import sql as dbsql
        except ImportError:
            raise ImportError(
                "databricks-sql-connector is required. "
                "Install with: pip install databricks-sql-connector"
            )
        self.conn = dbsql.connect(
            server_hostname=self.config.account,
            http_path=self.config.path,
            access_token=self.config.password,
            schema=self.config.warehouse_schema,
            catalog=self.config.database,
        )

    def disconnect(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _cursor(self, conn=None):
        c = conn or self.conn
        if not c:
            self.connect()
            c = self.conn
        return c.cursor()

    def execute(self, sql: str, conn=None) -> list[dict]:
        with self._cursor(conn) as cursor:
            cursor.execute(sql)
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            return []

    def execute_model(
        self, sql: str, table_name: str, materialized: str = "view",
        conn=None, unique_key: str | None = None,
        incremental_strategy: str = "append",
    ):
        safe = sanitize_name(table_name)

        if materialized == "incremental":
            if self.table_exists(table_name, conn=conn):
                if unique_key and incremental_strategy == "merge":
                    # Delta Lake MERGE — UPDATE SET * / INSERT * avoids enumerating columns
                    merge_sql = f"""
                        MERGE INTO {safe} AS target
                        USING ({sql}) AS source
                        ON target.`{unique_key}` = source.`{unique_key}`
                        WHEN MATCHED THEN UPDATE SET *
                        WHEN NOT MATCHED THEN INSERT *
                    """
                    with self._cursor(conn) as cursor:
                        cursor.execute(merge_sql)
                else:
                    with self._cursor(conn) as cursor:
                        cursor.execute(f"INSERT INTO {safe} {sql}")
            else:
                # First run — create Delta table (not a view)
                with self._cursor(conn) as cursor:
                    cursor.execute(f"CREATE TABLE {safe} AS {sql}")
            return

        self.drop_table(table_name, materialized, conn=conn)
        with self._cursor(conn) as cursor:
            if materialized == "table":
                cursor.execute(f"CREATE TABLE {safe} AS {sql}")
            elif materialized == "ephemeral":
                pass
            else:
                cursor.execute(f"CREATE OR REPLACE VIEW {safe} AS {sql}")

    def table_exists(self, table_name: str, conn=None) -> bool:
        safe = sanitize_name(table_name)
        with self._cursor(conn) as cursor:
            try:
                cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
                return cursor.fetchone() is not None
            except Exception:
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                    (table_name,),
                )
                row = cursor.fetchone()
                return row[0] > 0 if row else False

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        safe = sanitize_name(table_name)
        with self._cursor(conn) as cursor:
            try:
                cursor.execute(f"DESCRIBE {safe}")
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            except Exception:
                cursor.execute(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns WHERE table_name = ?",
                    (table_name,),
                )
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def drop_table(self, table_name: str, materialized: str = "view", conn=None):
        safe = sanitize_name(table_name)
        with self._cursor(conn) as cursor:
            if materialized == "view":
                cursor.execute(f"DROP VIEW IF EXISTS {safe}")
            else:
                cursor.execute(f"DROP TABLE IF EXISTS {safe}")

    def execute_snapshot(
        self,
        sql: str,
        table_name: str,
        unique_key: str,
        strategy: str = "timestamp",
        updated_at: str = "updated_at",
        conn=None,
    ) -> None:
        """SCD Type 2 snapshot execution (Delta Lake)."""
        safe = sanitize_name(table_name)
        uk = unique_key
        stage = f"_snap_stage_{table_name}"

        if not self.table_exists(table_name, conn=conn):
            dbt_updated_expr = (
                f'CAST(`{updated_at}` AS TIMESTAMP)'
                if strategy == "timestamp"
                else "CURRENT_TIMESTAMP()"
            )
            with self._cursor(conn) as cursor:
                cursor.execute(f"""
                    CREATE TABLE {safe} AS
                    SELECT *,
                        MD5(CAST(`{uk}` AS STRING))  AS _scd_id,
                        CURRENT_TIMESTAMP()          AS _valid_from,
                        CAST(NULL AS TIMESTAMP)      AS _valid_to,
                        TRUE                         AS _is_current,
                        {dbt_updated_expr}           AS _dbt_updated_at
                    FROM ({sql}) _src
                """)
            return

        # Create temp view to stage incoming data
        with self._cursor(conn) as cursor:
            cursor.execute(
                f"CREATE OR REPLACE TEMPORARY VIEW {stage} AS ({sql})"
            )

        if strategy == "timestamp":
            changed_cond = f'n.`{updated_at}` > s._dbt_updated_at'
        else:
            with self._cursor(conn) as cursor:
                cursor.execute(f"SELECT * FROM {stage} LIMIT 0")
                cols = [desc[0] for desc in cursor.description]
            check_cols = [col for col in cols if col != uk]
            if check_cols:
                changed_cond = " OR ".join(
                    f'n.`{col}` <> s.`{col}`'
                    for col in check_cols
                )
            else:
                changed_cond = "FALSE"

        # Close changed records via MERGE
        with self._cursor(conn) as cursor:
            cursor.execute(f"""
                MERGE INTO {safe} s
                USING (
                    SELECT n.`{uk}`
                    FROM {stage} n
                    JOIN {safe} s ON n.`{uk}` = s.`{uk}`
                    WHERE s._is_current = true AND ({changed_cond})
                ) changed
                ON s.`{uk}` = changed.`{uk}` AND s._is_current = true
                WHEN MATCHED THEN UPDATE SET
                    _valid_to = CURRENT_TIMESTAMP(),
                    _is_current = false
            """)

        dbt_updated_insert = (
            f'CAST(n.`{updated_at}` AS TIMESTAMP)'
            if strategy == "timestamp"
            else "CURRENT_TIMESTAMP()"
        )
        with self._cursor(conn) as cursor:
            cursor.execute(f"""
                INSERT INTO {safe}
                SELECT n.*,
                    MD5(CAST(n.`{uk}` AS STRING)) AS _scd_id,
                    CURRENT_TIMESTAMP()           AS _valid_from,
                    CAST(NULL AS TIMESTAMP)       AS _valid_to,
                    TRUE                          AS _is_current,
                    {dbt_updated_insert}          AS _dbt_updated_at
                FROM {stage} n
                WHERE NOT EXISTS (
                    SELECT 1 FROM {safe} s
                    WHERE s.`{uk}` = n.`{uk}` AND s._is_current = true
                )
            """)
