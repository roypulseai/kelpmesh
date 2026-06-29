"""Amazon Athena adapter for KelpMesh.

Install the driver:
    pip install kelpmesh[athena]

kelpmesh.yml:
    warehouse:
      type: athena
      host: us-east-1                        # AWS region
      database: my_glue_database
      path: "s3://my-bucket/athena-results/" # S3 staging dir for query results
      user: "{{ env_var('AWS_ACCESS_KEY_ID') }}"
      password: "{{ env_var('AWS_SECRET_ACCESS_KEY') }}"

Notes:
  - `host`  maps to the AWS region (e.g. us-east-1).
  - `path`  is the S3 staging directory used by Athena for result output.
  - `user`  / `password` are the AWS access key id / secret access key.
    Leave both unset to use the default credential chain (IAM role, env
    vars, ~/.aws/credentials, etc.).
  - Athena does not support INSERT INTO on CTAS tables; incremental runs
    use a CTAS-then-rename workaround.
  - External table creation requires `s3_location` to be passed as a
    keyword argument to execute_model via the `extra` dict (not yet
    exposed in the standard interface — extend as needed).
"""

from __future__ import annotations

from kelpmesh.adapters.base import WarehouseAdapter, sanitize_name
from kelpmesh.core.config import WarehouseConfig


class AthenaAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig) -> None:
        self.config = config
        self.conn = None

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def connect(self) -> None:
        try:
            import pyathena
        except ImportError:
            raise ImportError(
                "PyAthena not installed. Run: pip install kelpmesh[athena]"
            )

        kwargs: dict = {
            "s3_staging_dir": self.config.path or "",
            "region_name": self.config.host or "us-east-1",
        }
        if self.config.user:
            kwargs["aws_access_key_id"] = self.config.user
        if self.config.password:
            kwargs["aws_secret_access_key"] = self.config.password
        if self.config.database:
            kwargs["schema_name"] = self.config.database

        self.conn = pyathena.connect(**kwargs)

    def disconnect(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def _ensure_conn(self, conn=None):
        c = conn or self.conn
        if not c:
            self.connect()
            return self.conn
        return c

    # ------------------------------------------------------------------
    # execute
    # ------------------------------------------------------------------

    def execute(self, sql: str, conn=None) -> list[dict]:
        c = self._ensure_conn(conn)
        cursor = c.cursor()
        try:
            cursor.execute(sql)
            if cursor.description:
                cols = [d[0] for d in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
            return []
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # execute_model
    # ------------------------------------------------------------------

    def execute_model(
        self,
        sql: str,
        table_name: str,
        materialized: str = "view",
        conn=None,
        unique_key: str | None = None,
        incremental_strategy: str = "append",
    ) -> None:
        db = self.config.database or ""
        safe = f"`{db}`.`{table_name}`" if db else f"`{table_name}`"
        c = self._ensure_conn(conn)

        if materialized == "incremental":
            if self.table_exists(table_name, conn=c):
                # Athena CTAS tables do not support INSERT INTO.
                # Workaround: create a new CTAS table, then swap.
                tmp = f"_km_inc_{table_name}"
                safe_tmp = f"`{db}`.`{tmp}`" if db else f"`{tmp}`"
                # Drop any leftover temp table
                try:
                    self.execute(f"DROP TABLE IF EXISTS {safe_tmp}", conn=c)
                except Exception:
                    pass
                self.execute(f"CREATE TABLE {safe_tmp} AS {sql}", conn=c)
                self.execute(f"DROP TABLE IF EXISTS {safe}", conn=c)
                self.execute(
                    f"ALTER TABLE {safe_tmp} RENAME TO `{table_name}`", conn=c
                )
            else:
                self.execute(f"CREATE TABLE {safe} AS {sql}", conn=c)
            return

        self.drop_table(table_name, materialized, conn=c)
        if materialized == "table":
            self.execute(f"CREATE TABLE {safe} AS {sql}", conn=c)
        elif materialized == "ephemeral":
            pass
        else:
            self.execute(f"CREATE OR REPLACE VIEW {safe} AS {sql}", conn=c)

    # ------------------------------------------------------------------
    # table_exists
    # ------------------------------------------------------------------

    def table_exists(self, table_name: str, conn=None) -> bool:
        db = self.config.database or ""
        c = self._ensure_conn(conn)
        try:
            if db:
                rows = self.execute(
                    "SELECT COUNT(*) AS cnt FROM information_schema.tables "
                    f"WHERE table_schema = '{db}' AND table_name = '{table_name}'",
                    conn=c,
                )
            else:
                rows = self.execute(
                    "SELECT COUNT(*) AS cnt FROM information_schema.tables "
                    f"WHERE table_name = '{table_name}'",
                    conn=c,
                )
            return (rows[0].get("cnt") or 0) > 0 if rows else False
        except Exception:
            return False

    # ------------------------------------------------------------------
    # table_schema
    # ------------------------------------------------------------------

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        db = self.config.database or ""
        c = self._ensure_conn(conn)
        if db:
            rows = self.execute(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                f"WHERE table_schema = '{db}' AND table_name = '{table_name}' "
                "ORDER BY ordinal_position",
                conn=c,
            )
        else:
            rows = self.execute(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                f"WHERE table_name = '{table_name}' "
                "ORDER BY ordinal_position",
                conn=c,
            )
        return rows or []

    # ------------------------------------------------------------------
    # drop_table
    # ------------------------------------------------------------------

    def drop_table(self, table_name: str, materialized: str = "view", conn=None) -> None:
        db = self.config.database or ""
        safe = f"`{db}`.`{table_name}`" if db else f"`{table_name}`"
        c = self._ensure_conn(conn)
        if materialized == "view":
            self.execute(f"DROP VIEW IF EXISTS {safe}", conn=c)
        else:
            self.execute(f"DROP TABLE IF EXISTS {safe}", conn=c)

    # ------------------------------------------------------------------
    # execute_snapshot  (CTAS workaround — Athena has no MERGE INTO)
    # ------------------------------------------------------------------

    def execute_snapshot(
        self,
        sql: str,
        table_name: str,
        unique_key: str,
        strategy: str = "timestamp",
        updated_at: str = "updated_at",
        conn=None,
    ) -> None:
        """SCD Type 2 snapshot for Athena.

        Athena (Presto/Trino SQL engine) does not support MERGE INTO or UPDATE.
        The implementation uses a full-rebuild CTAS pattern:

        1. Read the existing snapshot table (if it exists).
        2. Identify changed rows by joining with incoming data.
        3. Expire changed rows by setting _valid_to / _is_current.
        4. Union everything into a new CTAS table, then swap.
        """
        db = self.config.database or ""
        safe = f"`{db}`.`{table_name}`" if db else f"`{table_name}`"
        stage = f"_km_snap_{table_name}"
        safe_stage = f"`{db}`.`{stage}`" if db else f"`{stage}`"
        new_table = f"_km_snap_new_{table_name}"
        safe_new = f"`{db}`.`{new_table}`" if db else f"`{new_table}`"
        c = self._ensure_conn(conn)

        try:
            if not self.table_exists(table_name, conn=c):
                if strategy == "timestamp":
                    dbt_updated_expr = f"CAST(\"{updated_at}\" AS TIMESTAMP)"
                else:
                    dbt_updated_expr = "current_timestamp"

                self.execute(f"""
                    CREATE TABLE {safe} AS
                    SELECT *,
                        to_hex(md5(to_utf8(CAST("{unique_key}" AS VARCHAR)))) AS _scd_id,
                        current_timestamp                                       AS _valid_from,
                        CAST(NULL AS TIMESTAMP)                                 AS _valid_to,
                        TRUE                                                    AS _is_current,
                        {dbt_updated_expr}                                      AS _dbt_updated_at
                    FROM ({sql}) _src
                """, conn=c)
                return

            # Stage incoming data as a view (Athena supports CREATE OR REPLACE VIEW)
            try:
                self.execute(f"DROP VIEW IF EXISTS {safe_stage}", conn=c)
            except Exception:
                pass
            self.execute(f"CREATE VIEW {safe_stage} AS {sql}", conn=c)

            if strategy == "timestamp":
                changed_cond = (
                    f"CAST(n.\"{updated_at}\" AS TIMESTAMP) > s._dbt_updated_at"
                )
            else:
                cols_info = self.table_schema(table_name, conn=c)
                audit_cols = {
                    "_scd_id", "_valid_from", "_valid_to",
                    "_is_current", "_dbt_updated_at",
                }
                check_cols = [
                    r["column_name"] for r in cols_info
                    if r["column_name"] != unique_key
                    and r["column_name"] not in audit_cols
                ]
                changed_cond = (
                    " OR ".join(
                        f"n.\"{col}\" IS DISTINCT FROM s.\"{col}\""
                        for col in check_cols
                    )
                    if check_cols
                    else "FALSE"
                )

            if strategy == "timestamp":
                dbt_updated_insert = f"CAST(n.\"{updated_at}\" AS TIMESTAMP)"
            else:
                dbt_updated_insert = "current_timestamp"

            # Build the full rebuilt snapshot in a new CTAS table
            try:
                self.execute(f"DROP TABLE IF EXISTS {safe_new}", conn=c)
            except Exception:
                pass

            self.execute(f"""
                CREATE TABLE {safe_new} AS
                -- Existing rows: expire changed ones, keep unchanged
                SELECT s.*,
                    CASE
                        WHEN n."{unique_key}" IS NOT NULL AND ({changed_cond})
                        THEN current_timestamp
                        ELSE s._valid_to
                    END AS _valid_to_new,
                    CASE
                        WHEN n."{unique_key}" IS NOT NULL AND ({changed_cond})
                        THEN FALSE
                        ELSE s._is_current
                    END AS _is_current_new
                FROM {safe} s
                LEFT JOIN {safe_stage} n ON n."{unique_key}" = s."{unique_key}"
                    AND s._is_current = TRUE

                UNION ALL

                -- New rows for changed or brand-new keys
                SELECT n.*,
                    to_hex(md5(to_utf8(CAST(n."{unique_key}" AS VARCHAR)))) AS _scd_id,
                    current_timestamp                                         AS _valid_from,
                    CAST(NULL AS TIMESTAMP)                                   AS _valid_to_new,
                    TRUE                                                      AS _is_current_new,
                    {dbt_updated_insert}                                      AS _dbt_updated_at
                FROM {safe_stage} n
                WHERE NOT EXISTS (
                    SELECT 1 FROM {safe} s
                    WHERE s."{unique_key}" = n."{unique_key}" AND s._is_current = TRUE
                )
                   OR EXISTS (
                    SELECT 1 FROM {safe} s
                    WHERE s."{unique_key}" = n."{unique_key}"
                      AND s._is_current = TRUE
                      AND ({changed_cond})
                )
            """, conn=c)

            # Swap: drop original, rename new
            self.execute(f"DROP TABLE IF EXISTS {safe}", conn=c)
            self.execute(
                f"ALTER TABLE {safe_new} RENAME TO `{table_name}`", conn=c
            )
            self.execute(f"DROP VIEW IF EXISTS {safe_stage}", conn=c)

        except Exception:
            try:
                self.execute(f"DROP VIEW IF EXISTS {safe_stage}", conn=c)
            except Exception:
                pass
            try:
                self.execute(f"DROP TABLE IF EXISTS {safe_new}", conn=c)
            except Exception:
                pass
            raise
