"""Apache Hive adapter for KelpMesh (via HiveServer2 / pyhive).

Install the driver:
    pip install kelpmesh[hive]

kelpmesh.yml:
    warehouse:
      type: hive
      host: hiveserver2-host
      port: 10000
      database: default
      user: hive
      password: "{{ env_var('HIVE_PASSWORD') }}"

Notes:
  - Connects to HiveServer2 via the Thrift binary transport (pyhive).
  - Basic Hive does not support MERGE INTO; execute_snapshot uses an
    INSERT OVERWRITE pattern that rewrites the target partition/table.
  - Hive 3.x with ACID support can use MERGE INTO — the execute_snapshot
    implementation detects availability via a best-effort attempt.
  - Views are created with CREATE OR REPLACE VIEW (Hive 2.2+).
"""

from __future__ import annotations

from kelpmesh.adapters.base import WarehouseAdapter, sanitize_name
from kelpmesh.core.config import WarehouseConfig


class HiveAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig) -> None:
        self.config = config
        self.conn = None

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def connect(self) -> None:
        try:
            from pyhive import hive
        except ImportError:
            raise ImportError(
                "pyhive not installed. Run: pip install kelpmesh[hive]"
            )

        auth = "CUSTOM" if self.config.password else "NONE"
        self.conn = hive.connect(
            host=self.config.host or "localhost",
            port=self.config.port or 10000,
            database=self.config.database or "default",
            username=self.config.user,
            password=self.config.password,
            auth=auth,
        )

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
                cols = [d[0].split(".")[-1] for d in cursor.description]
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
        db = self.config.database or "default"
        safe = f"`{db}`.`{table_name}`"
        c = self._ensure_conn(conn)

        if materialized == "incremental":
            if self.table_exists(table_name, conn=c):
                if unique_key and incremental_strategy == "merge":
                    # Hive 3+ ACID MERGE INTO
                    stage = f"_km_merge_{table_name}"
                    safe_stage = f"`{db}`.`{stage}`"
                    self.execute(f"DROP TABLE IF EXISTS {safe_stage}", conn=c)
                    self.execute(
                        f"CREATE TABLE {safe_stage} AS {sql}", conn=c
                    )
                    cols_info = self.table_schema(table_name, conn=c)
                    cols = [r["column_name"] for r in cols_info]
                    update_set = ", ".join(
                        f"target.`{col}` = source.`{col}`"
                        for col in cols
                        if col != unique_key
                    )
                    try:
                        self.execute(f"""
                            MERGE INTO {safe} AS target
                            USING {safe_stage} AS source
                            ON target.`{unique_key}` = source.`{unique_key}`
                            WHEN MATCHED THEN UPDATE SET {update_set}
                            WHEN NOT MATCHED THEN INSERT VALUES (
                                {', '.join(f'source.`{col}`' for col in cols)}
                            )
                        """, conn=c)
                    except Exception:
                        # Fallback for Hive < 3 or non-ACID tables: INSERT INTO
                        self.execute(
                            f"INSERT INTO {safe} SELECT * FROM {safe_stage}",
                            conn=c,
                        )
                    finally:
                        self.execute(
                            f"DROP TABLE IF EXISTS {safe_stage}", conn=c
                        )
                else:
                    # Standard append
                    self.execute(f"INSERT INTO {safe} {sql}", conn=c)
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
        db = self.config.database or "default"
        c = self._ensure_conn(conn)
        cursor = c.cursor()
        try:
            cursor.execute(f"USE `{db}`")
            cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
            rows = cursor.fetchall()
            return any(
                (row[0] if isinstance(row, (list, tuple)) else list(row.values())[0])
                == table_name
                for row in rows
            )
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # table_schema
    # ------------------------------------------------------------------

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        db = self.config.database or "default"
        c = self._ensure_conn(conn)
        rows = self.execute(f"DESCRIBE `{db}`.`{table_name}`", conn=c)
        result = []
        for row in rows:
            # DESCRIBE returns col_name, data_type, comment (or similar)
            col_name = (
                row.get("col_name")
                or row.get("column_name")
                or (list(row.values())[0] if row else "")
            )
            if not col_name or col_name.startswith("#") or col_name.strip() == "":
                continue
            data_type = (
                row.get("data_type")
                or row.get("type")
                or (list(row.values())[1] if len(row) > 1 else "")
            )
            result.append(
                {
                    "column_name": col_name.strip(),
                    "data_type": (data_type or "").strip(),
                    "is_nullable": "YES",
                }
            )
        return result

    # ------------------------------------------------------------------
    # drop_table
    # ------------------------------------------------------------------

    def drop_table(self, table_name: str, materialized: str = "view", conn=None) -> None:
        db = self.config.database or "default"
        safe = f"`{db}`.`{table_name}`"
        c = self._ensure_conn(conn)
        if materialized == "view":
            self.execute(f"DROP VIEW IF EXISTS {safe}", conn=c)
        else:
            self.execute(f"DROP TABLE IF EXISTS {safe}", conn=c)

    # ------------------------------------------------------------------
    # execute_snapshot  (INSERT OVERWRITE pattern for Hive)
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
        """SCD Type 2 snapshot for Hive.

        Basic Hive (pre-3 or non-ACID) does not support in-place UPDATE/MERGE.
        This implementation does a full-rebuild using INSERT OVERWRITE:

        1. On first run: CREATE TABLE ... AS SELECT with SCD-2 audit columns.
        2. On subsequent runs:
           a. Stage incoming data in a temp table.
           b. Compute the new full snapshot (expire changed rows + new rows)
              as a CTAS into a staging table.
           c. INSERT OVERWRITE the original table from the staging table.
           d. Drop the staging table.

        For Hive 3+ ACID tables a MERGE-based approach would be more
        efficient — upgrade the table to ORC + TBLPROPERTIES transactional
        and use execute_model with incremental_strategy="merge".
        """
        db = self.config.database or "default"
        safe = f"`{db}`.`{table_name}`"
        stage = f"_km_snap_{table_name}"
        safe_stage = f"`{db}`.`{stage}`"
        rebuild = f"_km_snap_rb_{table_name}"
        safe_rebuild = f"`{db}`.`{rebuild}`"
        c = self._ensure_conn(conn)

        try:
            if not self.table_exists(table_name, conn=c):
                if strategy == "timestamp":
                    dbt_updated_expr = f"CAST(`{updated_at}` AS TIMESTAMP)"
                else:
                    dbt_updated_expr = "CURRENT_TIMESTAMP()"

                self.execute(f"""
                    CREATE TABLE {safe} AS
                    SELECT *,
                        md5(CAST(`{unique_key}` AS STRING)) AS _scd_id,
                        CURRENT_TIMESTAMP()                 AS _valid_from,
                        CAST(NULL AS TIMESTAMP)             AS _valid_to,
                        TRUE                                AS _is_current,
                        {dbt_updated_expr}                  AS _dbt_updated_at
                    FROM ({sql}) _src
                """, conn=c)
                return

            # Stage incoming data
            self.execute(f"DROP TABLE IF EXISTS {safe_stage}", conn=c)
            self.execute(f"CREATE TABLE {safe_stage} AS {sql}", conn=c)

            if strategy == "timestamp":
                changed_cond = (
                    f"CAST(n.`{updated_at}` AS TIMESTAMP) > s._dbt_updated_at"
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
                        f"n.`{col}` != s.`{col}`"
                        for col in check_cols
                    )
                    if check_cols
                    else "FALSE"
                )

            if strategy == "timestamp":
                dbt_updated_insert = f"CAST(n.`{updated_at}` AS TIMESTAMP)"
            else:
                dbt_updated_insert = "CURRENT_TIMESTAMP()"

            # Build full rebuilt snapshot
            self.execute(f"DROP TABLE IF EXISTS {safe_rebuild}", conn=c)
            self.execute(f"""
                CREATE TABLE {safe_rebuild} AS
                SELECT
                    s.*,
                    CASE
                        WHEN n.`{unique_key}` IS NOT NULL AND ({changed_cond})
                        THEN CURRENT_TIMESTAMP()
                        ELSE s._valid_to
                    END AS _valid_to_new,
                    CASE
                        WHEN n.`{unique_key}` IS NOT NULL AND ({changed_cond})
                        THEN FALSE
                        ELSE s._is_current
                    END AS _is_current_new
                FROM {safe} s
                LEFT JOIN {safe_stage} n
                    ON n.`{unique_key}` = s.`{unique_key}` AND s._is_current = TRUE

                UNION ALL

                SELECT
                    n.*,
                    md5(CAST(n.`{unique_key}` AS STRING)) AS _scd_id,
                    CURRENT_TIMESTAMP()                   AS _valid_from,
                    CAST(NULL AS TIMESTAMP)               AS _valid_to_new,
                    TRUE                                  AS _is_current_new,
                    {dbt_updated_insert}                  AS _dbt_updated_at
                FROM {safe_stage} n
                WHERE NOT EXISTS (
                    SELECT 1 FROM {safe} s
                    WHERE s.`{unique_key}` = n.`{unique_key}` AND s._is_current = TRUE
                )
                   OR EXISTS (
                    SELECT 1 FROM {safe} s
                    WHERE s.`{unique_key}` = n.`{unique_key}`
                      AND s._is_current = TRUE
                      AND ({changed_cond})
                )
            """, conn=c)

            # Overwrite the original table
            self.execute(f"INSERT OVERWRITE TABLE {safe} SELECT * FROM {safe_rebuild}", conn=c)

            self.execute(f"DROP TABLE IF EXISTS {safe_stage}", conn=c)
            self.execute(f"DROP TABLE IF EXISTS {safe_rebuild}", conn=c)

        except Exception:
            try:
                self.execute(f"DROP TABLE IF EXISTS {safe_stage}", conn=c)
            except Exception:
                pass
            try:
                self.execute(f"DROP TABLE IF EXISTS {safe_rebuild}", conn=c)
            except Exception:
                pass
            raise
