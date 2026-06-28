from briq.adapters.base import WarehouseAdapter, sanitize_name
from briq.core.config import WarehouseConfig


class SnowflakeAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig):
        self.config = config
        self.conn = None

    def connect(self):
        import snowflake.connector
        self.conn = snowflake.connector.connect(
            account=self.config.account,
            user=self.config.user,
            password=self.config.password,
            role=self.config.role,
            warehouse=self.config.warehouse,
            database=self.config.database,
            schema=self.config.warehouse_schema,
        )

    def disconnect(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _ensure_conn(self, conn=None):
        c = conn or self.conn
        if not c:
            self.connect()
            return self.conn
        return c

    def execute(self, sql: str, conn=None) -> list[dict]:
        c = self._ensure_conn(conn)
        cur = c.cursor()
        cur.execute(sql)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchall() if cur.description else []
        return [dict(zip(columns, row)) for row in rows]

    def execute_model(
        self, sql: str, table_name: str, materialized: str = "view",
        conn=None, unique_key: str | None = None,
        incremental_strategy: str = "append",
    ):
        safe = sanitize_name(table_name)
        c = self._ensure_conn(conn)
        self.drop_table(table_name, materialized, conn=c)
        if materialized == "table":
            c.cursor().execute(f"CREATE TABLE {safe} AS {sql}")
        else:
            c.cursor().execute(f"CREATE OR REPLACE VIEW {safe} AS {sql}")

    def table_exists(self, table_name: str, conn=None) -> bool:
        c = self._ensure_conn(conn)
        cur = c.cursor()
        cur.execute(f"SHOW TABLES LIKE '{table_name}'")
        return cur.rowcount > 0

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        safe = sanitize_name(table_name)
        c = self._ensure_conn(conn)
        cur = c.cursor()
        cur.execute(f"DESCRIBE TABLE {safe}")
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def drop_table(self, table_name: str, materialized: str = "view", conn=None):
        safe = sanitize_name(table_name)
        c = self._ensure_conn(conn)
        cur = c.cursor()
        if materialized == "view":
            cur.execute(f"DROP VIEW IF EXISTS {safe}")
        else:
            cur.execute(f"DROP TABLE IF EXISTS {safe}")
