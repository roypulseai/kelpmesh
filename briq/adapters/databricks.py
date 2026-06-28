from briq.adapters.base import WarehouseAdapter, sanitize_name
from briq.core.config import WarehouseConfig


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
