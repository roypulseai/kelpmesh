"""Amazon Redshift adapter — Postgres-compatible with Redshift MERGE for incremental."""

import psycopg2
from briq.adapters.base import WarehouseAdapter, sanitize_name
from briq.core.config import WarehouseConfig


class RedshiftAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig):
        self.config = config
        self.conn = None

    def connect(self):
        self.conn = psycopg2.connect(
            host=self.config.host,
            port=self.config.port or 5439,
            dbname=self.config.database,
            user=self.config.user,
            password=self.config.password,
            sslmode="require",
        )
        self.conn.autocommit = True

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
        with c.cursor() as cur:
            cur.execute(sql)
            if cur.description:
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
            return []

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
                    # Redshift MERGE (supported since 2022)
                    with c.cursor() as cur:
                        cur.execute(f"SELECT * FROM ({sql}) AS _briq_src LIMIT 0")
                        cols = [desc[0] for desc in cur.description]
                    col_list = ", ".join(f'"{col}"' for col in cols)
                    source_vals = ", ".join(f'source."{col}"' for col in cols)
                    update_set = ", ".join(
                        f'"{col}" = source."{col}"'
                        for col in cols if col != unique_key
                    )
                    merge_sql = f"""
                        MERGE INTO {safe}
                        USING ({sql}) AS source
                        ON {safe}."{unique_key}" = source."{unique_key}"
                        WHEN MATCHED THEN UPDATE SET {update_set}
                        WHEN NOT MATCHED THEN INSERT ({col_list}) VALUES ({source_vals})
                    """
                    with c.cursor() as cur:
                        cur.execute(merge_sql)
                else:
                    with c.cursor() as cur:
                        cur.execute(f"INSERT INTO {safe} {sql}")
            else:
                with c.cursor() as cur:
                    cur.execute(f"CREATE TABLE {safe} AS {sql}")
            return

        self.drop_table(table_name, materialized, conn=c)
        with c.cursor() as cur:
            if materialized == "table":
                cur.execute(f"CREATE TABLE {safe} AS {sql}")
            elif materialized == "ephemeral":
                pass
            else:
                cur.execute(f"CREATE OR REPLACE VIEW {safe} AS {sql}")

    def table_exists(self, table_name: str, conn=None) -> bool:
        c = self._ensure_conn(conn)
        with c.cursor() as cur:
            cur.execute(
                "SELECT EXISTS(SELECT FROM information_schema.tables WHERE table_name = %s)",
                (table_name,),
            )
            return cur.fetchone()[0]

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        c = self._ensure_conn(conn)
        with c.cursor() as cur:
            cur.execute(
                """SELECT column_name, data_type, is_nullable
                   FROM information_schema.columns WHERE table_name = %s""",
                (table_name,),
            )
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def drop_table(self, table_name: str, materialized: str = "view", conn=None):
        safe = sanitize_name(table_name)
        c = self._ensure_conn(conn)
        with c.cursor() as cur:
            if materialized == "view":
                cur.execute(f"DROP VIEW IF EXISTS {safe}")
            else:
                cur.execute(f"DROP TABLE IF EXISTS {safe}")
