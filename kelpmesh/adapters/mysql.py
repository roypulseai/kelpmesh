"""MySQL / MariaDB adapter for KelpMesh.

Install the driver:
    pip install kelpmesh[mysql]

kelpmesh.yml:
    warehouse:
      type: mysql
      host: 127.0.0.1
      port: 3306
      database: my_database
      user: root
      password: "{{ env_var('MYSQL_PASSWORD') }}"
"""

from kelpmesh.adapters.base import WarehouseAdapter, sanitize_name
from kelpmesh.core.config import WarehouseConfig


class MySQLAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig) -> None:
        self.config = config
        self.conn = None

    def connect(self) -> None:
        try:
            import mysql.connector
        except ImportError:
            raise ImportError(
                "MySQL driver not installed. Run: pip install kelpmesh[mysql]"
            )
        self.conn = mysql.connector.connect(
            host=self.config.host or "127.0.0.1",
            port=self.config.port or 3306,
            database=self.config.database,
            user=self.config.user,
            password=self.config.password,
            autocommit=True,
            charset="utf8mb4",
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

    def execute(self, sql: str, conn=None) -> list[dict]:
        c = self._ensure_conn(conn)
        cursor = c.cursor(dictionary=True)
        try:
            cursor.execute(sql)
            if cursor.description:
                return cursor.fetchall()
            return []
        finally:
            cursor.close()

    def execute_model(
        self, sql: str, table_name: str, materialized: str = "view",
        conn=None, unique_key: str | None = None,
        incremental_strategy: str = "append",
    ) -> None:
        # MySQL uses backtick quoting
        safe = f"`{table_name}`"
        c = self._ensure_conn(conn)

        if materialized == "incremental":
            if self.table_exists(table_name, conn=c):
                if unique_key and incremental_strategy == "merge":
                    # MySQL INSERT ... ON DUPLICATE KEY UPDATE
                    temp = f"_km_merge_{table_name}"
                    safe_temp = f"`{temp}`"
                    self.execute(f"CREATE TEMPORARY TABLE {safe_temp} AS {sql}", conn=c)
                    cols_info = self.table_schema(table_name, conn=c)
                    cols = [r["column_name"] for r in cols_info]
                    col_list = ", ".join(f"`{col}`" for col in cols)
                    update_set = ", ".join(
                        f"`{col}` = VALUES(`{col}`)"
                        for col in cols if col != unique_key
                    )
                    self.execute(f"""
                        INSERT INTO {safe} ({col_list})
                        SELECT {col_list} FROM {safe_temp}
                        ON DUPLICATE KEY UPDATE {update_set}
                    """, conn=c)
                    self.execute(f"DROP TEMPORARY TABLE IF EXISTS {safe_temp}", conn=c)
                else:
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

    def table_exists(self, table_name: str, conn=None) -> bool:
        c = self._ensure_conn(conn)
        cursor = c.cursor()
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = %s",
                (table_name,),
            )
            return cursor.fetchone()[0] > 0
        finally:
            cursor.close()

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        c = self._ensure_conn(conn)
        cursor = c.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s "
                "ORDER BY ordinal_position",
                (table_name,),
            )
            return cursor.fetchall()
        finally:
            cursor.close()

    def drop_table(self, table_name: str, materialized: str = "view", conn=None) -> None:
        safe = f"`{table_name}`"
        c = self._ensure_conn(conn)
        if materialized == "view":
            self.execute(f"DROP VIEW IF EXISTS {safe}", conn=c)
        else:
            self.execute(f"DROP TABLE IF EXISTS {safe}", conn=c)

    def execute_snapshot(
        self, sql: str, table_name: str, unique_key: str,
        strategy: str = "timestamp", updated_at: str = "updated_at", conn=None,
    ) -> None:
        """SCD Type 2 snapshot for MySQL."""
        safe = f"`{table_name}`"
        uk = unique_key
        c = self._ensure_conn(conn)
        stage = f"_km_snap_{table_name}"
        safe_stage = f"`{stage}`"

        try:
            if not self.table_exists(table_name, conn=c):
                dbt_updated_expr = (
                    f"CAST(`{updated_at}` AS DATETIME)"
                    if strategy == "timestamp"
                    else "NOW()"
                )
                self.execute(f"""
                    CREATE TABLE {safe} AS
                    SELECT *,
                        MD5(CAST(`{uk}` AS CHAR))  AS _scd_id,
                        NOW()                       AS _valid_from,
                        NULL                        AS _valid_to,
                        TRUE                        AS _is_current,
                        {dbt_updated_expr}          AS _dbt_updated_at
                    FROM ({sql}) _src
                """, conn=c)
                return

            self.execute(f"DROP TABLE IF EXISTS {safe_stage}", conn=c)
            self.execute(f"CREATE TEMPORARY TABLE {safe_stage} AS {sql}", conn=c)

            if strategy == "timestamp":
                changed_cond = f"CAST(n.`{updated_at}` AS DATETIME) > s._dbt_updated_at"
            else:
                cols_info = self.table_schema(table_name, conn=c)
                audit = {"_scd_id", "_valid_from", "_valid_to", "_is_current", "_dbt_updated_at"}
                check_cols = [
                    r["column_name"] for r in cols_info
                    if r["column_name"] != uk and r["column_name"] not in audit
                ]
                changed_cond = (
                    " OR ".join(f"n.`{col}` IS DISTINCT FROM s.`{col}`" for col in check_cols)
                    if check_cols else "FALSE"
                )

            self.execute(f"""
                UPDATE {safe} s
                JOIN {safe_stage} n ON n.`{uk}` = s.`{uk}`
                SET s._valid_to = NOW(), s._is_current = FALSE
                WHERE s._is_current = TRUE AND ({changed_cond})
            """, conn=c)

            dbt_updated_insert = (
                f"CAST(n.`{updated_at}` AS DATETIME)"
                if strategy == "timestamp"
                else "NOW()"
            )
            self.execute(f"""
                INSERT INTO {safe}
                SELECT n.*,
                    MD5(CAST(n.`{uk}` AS CHAR)) AS _scd_id,
                    NOW()                        AS _valid_from,
                    NULL                         AS _valid_to,
                    TRUE                         AS _is_current,
                    {dbt_updated_insert}         AS _dbt_updated_at
                FROM {safe_stage} n
                WHERE NOT EXISTS (
                    SELECT 1 FROM {safe} s
                    WHERE s.`{uk}` = n.`{uk}` AND s._is_current = TRUE
                )
            """, conn=c)

            self.execute(f"DROP TABLE IF EXISTS {safe_stage}", conn=c)
        except Exception:
            self.execute(f"DROP TABLE IF EXISTS {safe_stage}", conn=c)
            raise
