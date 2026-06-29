"""Amazon Redshift adapter — Postgres-compatible with Redshift MERGE for incremental."""

import psycopg2
from kelpmesh.adapters.base import WarehouseAdapter, sanitize_name
from kelpmesh.core.config import WarehouseConfig


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
                        cur.execute(f"SELECT * FROM ({sql}) AS _km_src LIMIT 0")
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

    def execute_snapshot(
        self,
        sql: str,
        table_name: str,
        unique_key: str,
        strategy: str = "timestamp",
        updated_at: str = "updated_at",
        conn=None,
    ) -> None:
        """SCD Type 2 snapshot — tracks full row history in Redshift."""
        safe = sanitize_name(table_name)
        uk = unique_key
        c = self._ensure_conn(conn)
        stage = f"_km_snap_{table_name}"
        safe_stage = sanitize_name(stage)

        try:
            if not self.table_exists(table_name, conn=c):
                dbt_updated_expr = (
                    f'CAST("{updated_at}" AS TIMESTAMP)'
                    if strategy == "timestamp"
                    else "CURRENT_TIMESTAMP"
                )
                with c.cursor() as cur:
                    cur.execute(f"""
                        CREATE TABLE {safe} AS
                        SELECT *,
                            MD5(CAST("{uk}" AS VARCHAR))  AS _scd_id,
                            CURRENT_TIMESTAMP             AS _valid_from,
                            NULL::TIMESTAMP               AS _valid_to,
                            TRUE                          AS _is_current,
                            {dbt_updated_expr}            AS _dbt_updated_at
                        FROM ({sql}) _src
                    """)
                return

            with c.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {safe_stage}")
                cur.execute(f"CREATE TEMP TABLE {safe_stage} AS {sql}")

            if strategy == "timestamp":
                changed_cond = f'CAST(n."{updated_at}" AS TIMESTAMP) > s._dbt_updated_at'
            else:
                with c.cursor() as cur:
                    cur.execute(f"SELECT * FROM {safe_stage} LIMIT 0")
                    cols = [desc[0] for desc in cur.description]
                check_cols = [col for col in cols if col != uk]
                changed_cond = (
                    " OR ".join(f'n."{col}" IS DISTINCT FROM s."{col}"' for col in check_cols)
                    if check_cols else "FALSE"
                )

            # Redshift UPDATE...FROM: target table cannot have an alias
            with c.cursor() as cur:
                cur.execute(f"""
                    UPDATE {safe}
                    SET _valid_to = CURRENT_TIMESTAMP, _is_current = false
                    FROM {safe_stage} n
                    WHERE {safe}."{uk}" = n."{uk}"
                      AND {safe}._is_current = true
                      AND ({changed_cond})
                """)

            dbt_updated_insert = (
                f'CAST(n."{updated_at}" AS TIMESTAMP)'
                if strategy == "timestamp"
                else "CURRENT_TIMESTAMP"
            )
            with c.cursor() as cur:
                cur.execute(f"""
                    INSERT INTO {safe}
                    SELECT n.*,
                        MD5(CAST(n."{uk}" AS VARCHAR)) AS _scd_id,
                        CURRENT_TIMESTAMP              AS _valid_from,
                        NULL::TIMESTAMP                AS _valid_to,
                        TRUE                           AS _is_current,
                        {dbt_updated_insert}           AS _dbt_updated_at
                    FROM {safe_stage} n
                    WHERE NOT EXISTS (
                        SELECT 1 FROM {safe} s
                        WHERE s."{uk}" = n."{uk}" AND s._is_current = true
                    )
                """)

            with c.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {safe_stage}")
        except Exception:
            try:
                with c.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {safe_stage}")
            except Exception:
                pass
            raise


    def execute_materialized_view(self, sql: str, table_name: str, conn=None) -> None:
        c = self._ensure_conn(conn)
        safe = f'"{table_name}"'
        with c.cursor() as cur:
            cur.execute(f"DROP MATERIALIZED VIEW IF EXISTS {safe} CASCADE")
            cur.execute(f"CREATE MATERIALIZED VIEW {safe} AS {sql}")
