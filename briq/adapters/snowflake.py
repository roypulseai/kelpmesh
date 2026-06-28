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
        cur.close()
        return [dict(zip(columns, row)) for row in rows]

    def execute_model(
        self, sql: str, table_name: str, materialized: str = "view",
        conn=None, unique_key: str | None = None,
        incremental_strategy: str = "append",
    ):
        safe = sanitize_name(table_name)
        c = self._ensure_conn(conn)

        if materialized == "incremental":
            if self.table_exists(table_name, conn=c):
                if unique_key and incremental_strategy == "merge":
                    # Inspect columns via LIMIT 0 then build a MERGE statement
                    cur = c.cursor()
                    cur.execute(f"SELECT * FROM ({sql}) AS _briq_src LIMIT 0")
                    cols = [desc[0] for desc in cur.description]
                    cur.close()
                    col_list = ", ".join(f'"{col}"' for col in cols)
                    update_set = ", ".join(
                        f'target."{col}" = source."{col}"'
                        for col in cols if col != unique_key
                    )
                    source_vals = ", ".join(f'source."{col}"' for col in cols)
                    merge_sql = f"""
                        MERGE INTO {safe} AS target
                        USING ({sql}) AS source
                        ON target."{unique_key}" = source."{unique_key}"
                        WHEN MATCHED THEN UPDATE SET {update_set}
                        WHEN NOT MATCHED THEN INSERT ({col_list}) VALUES ({source_vals})
                    """
                    c.cursor().execute(merge_sql)
                else:
                    c.cursor().execute(f"INSERT INTO {safe} {sql}")
            else:
                c.cursor().execute(f"CREATE TABLE {safe} AS {sql}")
            return

        self.drop_table(table_name, materialized, conn=c)
        if materialized == "table":
            c.cursor().execute(f"CREATE TABLE {safe} AS {sql}")
        elif materialized == "ephemeral":
            pass
        else:
            c.cursor().execute(f"CREATE OR REPLACE VIEW {safe} AS {sql}")

    def table_exists(self, table_name: str, conn=None) -> bool:
        c = self._ensure_conn(conn)
        cur = c.cursor()
        cur.execute(f"SHOW TABLES LIKE '{table_name}'")
        result = cur.rowcount > 0
        cur.close()
        return result

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        safe = sanitize_name(table_name)
        c = self._ensure_conn(conn)
        cur = c.cursor()
        cur.execute(f"DESCRIBE TABLE {safe}")
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        cur.close()
        return rows

    def drop_table(self, table_name: str, materialized: str = "view", conn=None):
        safe = sanitize_name(table_name)
        c = self._ensure_conn(conn)
        cur = c.cursor()
        if materialized == "view":
            cur.execute(f"DROP VIEW IF EXISTS {safe}")
        else:
            cur.execute(f"DROP TABLE IF EXISTS {safe}")
        cur.close()
