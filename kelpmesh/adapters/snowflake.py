from kelpmesh.adapters.base import WarehouseAdapter, sanitize_name
from kelpmesh.core.config import WarehouseConfig


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
        safe = sanitize_name(table_name)
        uk = unique_key
        c = self._ensure_conn(conn)
        stage = f"_briq_snap_{table_name}"

        try:
            if not self.table_exists(table_name, conn=c):
                dbt_updated_expr = (
                    f'CAST("{updated_at}" AS TIMESTAMP)'
                    if strategy == "timestamp"
                    else "CURRENT_TIMESTAMP()"
                )
                cur = c.cursor()
                cur.execute(f"""
                    CREATE TABLE {safe} AS
                    SELECT *,
                        MD5(CAST("{uk}" AS VARCHAR)) AS _scd_id,
                        CURRENT_TIMESTAMP()          AS _valid_from,
                        NULL::TIMESTAMP              AS _valid_to,
                        TRUE                         AS _is_current,
                        {dbt_updated_expr}           AS _dbt_updated_at
                    FROM ({sql}) _src
                """)
                cur.close()
                return

            cur = c.cursor()
            cur.execute(f"DROP TABLE IF EXISTS {stage}")
            cur.execute(f"CREATE TEMP TABLE {stage} AS {sql}")

            if strategy == "timestamp":
                changed_cond = f'CAST(n."{updated_at}" AS TIMESTAMP) > s._dbt_updated_at'
            else:
                cur.execute(f"SELECT * FROM {stage} LIMIT 0")
                cols = [desc[0] for desc in cur.description]
                check_cols = [col for col in cols if col != uk]
                if check_cols:
                    changed_cond = " OR ".join(
                        f'n."{col}" <> s."{col}"'
                        for col in check_cols
                    )
                else:
                    changed_cond = "FALSE"
            cur.close()

            # Expire changed records — Snowflake UPDATE...FROM subquery
            cur = c.cursor()
            cur.execute(f"""
                UPDATE {safe} t
                SET _valid_to = CURRENT_TIMESTAMP(), _is_current = false
                FROM (
                    SELECT n."{uk}"
                    FROM {stage} n
                    JOIN {safe} s ON n."{uk}" = s."{uk}"
                    WHERE s._is_current = true AND ({changed_cond})
                ) changed
                WHERE t."{uk}" = changed."{uk}" AND t._is_current = true
            """)
            cur.close()

            dbt_updated_insert = (
                f'CAST(n."{updated_at}" AS TIMESTAMP)'
                if strategy == "timestamp"
                else "CURRENT_TIMESTAMP()"
            )
            cur = c.cursor()
            cur.execute(f"""
                INSERT INTO {safe}
                SELECT n.*,
                    MD5(CAST(n."{uk}" AS VARCHAR)) AS _scd_id,
                    CURRENT_TIMESTAMP()            AS _valid_from,
                    NULL::TIMESTAMP                AS _valid_to,
                    TRUE                           AS _is_current,
                    {dbt_updated_insert}           AS _dbt_updated_at
                FROM {stage} n
                WHERE NOT EXISTS (
                    SELECT 1 FROM {safe} s
                    WHERE s."{uk}" = n."{uk}" AND s._is_current = true
                )
            """)
            cur.close()

            cur = c.cursor()
            cur.execute(f"DROP TABLE IF EXISTS {stage}")
            cur.close()
        except Exception:
            try:
                _cur = c.cursor()
                _cur.execute(f"DROP TABLE IF EXISTS {stage}")
                _cur.close()
            except Exception:
                pass
            raise
