"""Apache Spark adapter for KelpMesh (Spark Connect and Thrift/HiveServer2).

Install the driver:
    pip install kelpmesh[spark]

kelpmesh.yml (Spark Connect):
    warehouse:
      type: spark
      path: "sc://spark-connect-host:15002"
      database: default

kelpmesh.yml (Thrift / HiveServer2):
    warehouse:
      type: spark
      host: spark-thrift-host
      port: 10000
      database: default
      user: spark
      password: "{{ env_var('SPARK_PASSWORD') }}"

Notes:
  - If `path` starts with "sc://" a Spark Connect remote session is used.
  - Otherwise a pyhive Thrift connection is opened against `host`:`port`.
  - Delta Lake tables are required for execute_snapshot (MERGE INTO).
"""

from __future__ import annotations

from kelpmesh.adapters.base import WarehouseAdapter, sanitize_name
from kelpmesh.core.config import WarehouseConfig


class SparkAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig) -> None:
        self.config = config
        self.conn = None        # pyhive connection (Thrift path)
        self._spark = None      # SparkSession (Spark Connect path)

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _use_connect(self) -> bool:
        """Return True when the Spark Connect gRPC URL is configured."""
        return bool(self.config.path and self.config.path.startswith("sc://"))

    def connect(self) -> None:
        if self._use_connect():
            self._connect_spark_connect()
        else:
            self._connect_thrift()

    def _connect_spark_connect(self) -> None:
        try:
            from pyspark.sql import SparkSession
        except ImportError:
            raise ImportError(
                "PySpark not installed. Run: pip install kelpmesh[spark]"
            )
        self._spark = SparkSession.builder.remote(self.config.path).getOrCreate()
        db = self.config.database or "default"
        self._spark.sql(f"USE {db}")

    def _connect_thrift(self) -> None:
        try:
            from pyhive import hive as pyhive_hive
        except ImportError:
            raise ImportError(
                "pyhive not installed. Run: pip install kelpmesh[spark]"
            )
        self.conn = pyhive_hive.connect(
            host=self.config.host or "localhost",
            port=self.config.port or 15001,
            database=self.config.database or "default",
            username=self.config.user,
            password=self.config.password,
            auth="CUSTOM" if self.config.password else "NONE",
        )

    def disconnect(self) -> None:
        if self._spark:
            self._spark.stop()
            self._spark = None
        if self.conn:
            self.conn.close()
            self.conn = None

    def _ensure_conn(self, conn=None):
        """Return the active connection/session, opening one if needed."""
        if self._use_connect():
            if self._spark is None:
                self.connect()
            return self._spark
        c = conn or self.conn
        if not c:
            self.connect()
            return self.conn
        return c

    # ------------------------------------------------------------------
    # execute
    # ------------------------------------------------------------------

    def execute(self, sql: str, conn=None) -> list[dict]:
        active = self._ensure_conn(conn)

        if self._use_connect():
            # SparkSession — returns a DataFrame
            df = active.sql(sql)
            try:
                rows = df.collect()
                cols = df.columns
                return [dict(zip(cols, row)) for row in rows]
            except Exception:
                # DDL statements (CREATE, DROP, INSERT) return empty
                return []

        # Thrift path via pyhive
        cursor = active.cursor()
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
        db = self.config.database or "default"
        safe = f"`{db}`.`{table_name}`"
        active = self._ensure_conn(conn)

        if materialized == "incremental":
            if self.table_exists(table_name, conn=active):
                if unique_key and incremental_strategy == "merge":
                    # Overwrite matching partitions via a temp view + MERGE
                    stage = f"_km_merge_{table_name}"
                    self.execute(f"CREATE OR REPLACE TEMP VIEW `{stage}` AS {sql}", conn=active)
                    self.execute(f"""
                        MERGE INTO {safe} AS target
                        USING `{stage}` AS source
                        ON target.`{unique_key}` = source.`{unique_key}`
                        WHEN MATCHED THEN UPDATE SET *
                        WHEN NOT MATCHED THEN INSERT *
                    """, conn=active)
                    self.execute(f"DROP VIEW IF EXISTS `{stage}`", conn=active)
                else:
                    # incremental append
                    self.execute(f"INSERT INTO {safe} {sql}", conn=active)
            else:
                self.execute(f"CREATE OR REPLACE TABLE {safe} AS {sql}", conn=active)
            return

        self.drop_table(table_name, materialized, conn=active)
        if materialized == "table":
            self.execute(f"CREATE OR REPLACE TABLE {safe} AS {sql}", conn=active)
        elif materialized == "ephemeral":
            pass
        else:
            self.execute(f"CREATE OR REPLACE VIEW {safe} AS {sql}", conn=active)

    # ------------------------------------------------------------------
    # table_exists
    # ------------------------------------------------------------------

    def table_exists(self, table_name: str, conn=None) -> bool:
        active = self._ensure_conn(conn)
        db = self.config.database or "default"

        if self._use_connect():
            return active.catalog.tableExists(table_name, dbName=db)

        # Thrift — use SHOW TABLES
        cursor = active.cursor()
        try:
            cursor.execute(f"SHOW TABLES IN `{db}` LIKE '{table_name}'")
            rows = cursor.fetchall()
            return len(rows) > 0
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # table_schema
    # ------------------------------------------------------------------

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        db = self.config.database or "default"
        active = self._ensure_conn(conn)

        if self._use_connect():
            schema = active.table(f"{db}.{table_name}").schema
            return [
                {
                    "column_name": field.name,
                    "data_type": str(field.dataType),
                    "is_nullable": "YES" if field.nullable else "NO",
                }
                for field in schema.fields
            ]

        # Thrift — DESCRIBE
        rows = self.execute(f"DESCRIBE `{db}`.`{table_name}`", conn=active)
        result = []
        for row in rows:
            col_name = row.get("col_name") or row.get("column_name") or ""
            if not col_name or col_name.startswith("#"):
                continue
            result.append(
                {
                    "column_name": col_name,
                    "data_type": row.get("data_type") or "",
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
        active = self._ensure_conn(conn)
        if materialized == "view":
            self.execute(f"DROP VIEW IF EXISTS {safe}", conn=active)
        else:
            self.execute(f"DROP TABLE IF EXISTS {safe}", conn=active)

    # ------------------------------------------------------------------
    # execute_snapshot  (Delta Lake MERGE INTO — SCD Type 2)
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
        """SCD Type 2 snapshot for Spark / Delta Lake.

        Requires the target table to be a Delta table.  On first run the
        snapshot table is created from the source query with the four SCD-2
        audit columns appended (_scd_id, _valid_from, _valid_to, _is_current).
        Subsequent runs use Delta MERGE INTO to expire changed rows and insert
        fresh ones.
        """
        db = self.config.database or "default"
        safe = f"`{db}`.`{table_name}`"
        stage = f"_km_snap_{table_name}"
        active = self._ensure_conn(conn)

        try:
            if not self.table_exists(table_name, conn=active):
                if strategy == "timestamp":
                    dbt_updated_expr = f"CAST(`{updated_at}` AS TIMESTAMP)"
                else:
                    dbt_updated_expr = "current_timestamp()"

                self.execute(f"""
                    CREATE TABLE {safe}
                    USING DELTA
                    AS
                    SELECT *,
                        md5(cast(`{unique_key}` AS STRING)) AS _scd_id,
                        current_timestamp()                  AS _valid_from,
                        CAST(NULL AS TIMESTAMP)              AS _valid_to,
                        TRUE                                 AS _is_current,
                        {dbt_updated_expr}                   AS _dbt_updated_at
                    FROM ({sql}) _src
                """, conn=active)
                return

            # Stage incoming data
            self.execute(
                f"CREATE OR REPLACE TEMP VIEW `{stage}` AS {sql}",
                conn=active,
            )

            if strategy == "timestamp":
                changed_cond = (
                    f"CAST(source.`{updated_at}` AS TIMESTAMP) > target._dbt_updated_at"
                )
            else:
                cols_info = self.table_schema(table_name, conn=active)
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
                        f"source.`{col}` IS DISTINCT FROM target.`{col}`"
                        for col in check_cols
                    )
                    if check_cols
                    else "FALSE"
                )

            # Expire changed rows
            self.execute(f"""
                MERGE INTO {safe} AS target
                USING `{stage}` AS source
                ON target.`{unique_key}` = source.`{unique_key}`
                   AND target._is_current = TRUE
                WHEN MATCHED AND ({changed_cond}) THEN
                    UPDATE SET
                        target._valid_to    = current_timestamp(),
                        target._is_current  = FALSE
            """, conn=active)

            # Insert new / changed rows
            if strategy == "timestamp":
                dbt_updated_insert = f"CAST(source.`{updated_at}` AS TIMESTAMP)"
            else:
                dbt_updated_insert = "current_timestamp()"

            self.execute(f"""
                MERGE INTO {safe} AS target
                USING (
                    SELECT source.*
                    FROM `{stage}` source
                    LEFT JOIN {safe} existing
                        ON existing.`{unique_key}` = source.`{unique_key}`
                       AND existing._is_current = TRUE
                    WHERE existing.`{unique_key}` IS NULL
                ) AS new_rows
                ON FALSE
                WHEN NOT MATCHED THEN
                    INSERT (
                        *,
                        _scd_id,
                        _valid_from,
                        _valid_to,
                        _is_current,
                        _dbt_updated_at
                    )
                    VALUES (
                        new_rows.*,
                        md5(cast(new_rows.`{unique_key}` AS STRING)),
                        current_timestamp(),
                        CAST(NULL AS TIMESTAMP),
                        TRUE,
                        {dbt_updated_insert}
                    )
            """, conn=active)

            self.execute(f"DROP VIEW IF EXISTS `{stage}`", conn=active)

        except Exception:
            try:
                self.execute(f"DROP VIEW IF EXISTS `{stage}`", conn=active)
            except Exception:
                pass
            raise
