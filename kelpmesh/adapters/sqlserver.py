"""SQL Server / Azure Synapse adapter for KelpMesh.

Install the driver:
    pip install kelpmesh[sqlserver]

Requirements:
    - "ODBC Driver 18 for SQL Server" installed on the host OS
      Windows: included with SQL Server, or download from Microsoft
      Linux:   sudo apt install msodbcsql18
      macOS:   brew install msodbcsql18

kelpmesh.yml:
    warehouse:
      type: sqlserver
      host: my-server.database.windows.net
      port: 1433
      database: my_database
      user: sa
      password: "{{ env_var('MSSQL_PASSWORD') }}"

Azure Synapse (dedicated SQL pool):
    warehouse:
      type: sqlserver           # Synapse speaks T-SQL
      host: my-workspace.sql.azuresynapse.net
      port: 1433
      database: my_pool
      user: sqladmin
      password: "{{ env_var('SYNAPSE_PASSWORD') }}"

    connection_string override (optional — skips host/port/database/user/password):
      connection_string: "Driver={ODBC Driver 18 for SQL Server};Server=...;Database=...;..."
"""

from __future__ import annotations

from kelpmesh.adapters.base import WarehouseAdapter
from kelpmesh.core.config import WarehouseConfig

_DRIVERS = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
]


class SQLServerAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig) -> None:
        self.config = config
        self.conn = None

    def _build_connection_string(self) -> str:
        if self.config.connection_string:
            return self.config.connection_string
        driver = self._detect_driver()
        port = self.config.port or 1433
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={self.config.host},{port};"
            f"DATABASE={self.config.database};"
            f"UID={self.config.user};"
            f"PWD={self.config.password};"
            "TrustServerCertificate=yes;"
            "Encrypt=yes;"
        )

    def _detect_driver(self) -> str:
        try:
            import pyodbc
            available = [d for d in pyodbc.drivers() if "SQL Server" in d]
            for preferred in _DRIVERS:
                if preferred in available:
                    return preferred
            if available:
                return available[0]
        except ImportError:
            pass
        return _DRIVERS[0]

    def connect(self) -> None:
        try:
            import pyodbc
        except ImportError:
            raise ImportError(
                "pyodbc not installed. Run: pip install kelpmesh[sqlserver]\n"
                "Also install the OS-level ODBC driver:\n"
                "  Windows: download from https://aka.ms/odbc18\n"
                "  Linux:   sudo apt install msodbcsql18\n"
                "  macOS:   brew install msodbcsql18"
            )
        cs = self._build_connection_string()
        self.conn = pyodbc.connect(cs, autocommit=True)

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
        cursor = c.cursor()
        try:
            cursor.execute(sql)
            if cursor.description:
                cols = [d[0] for d in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
            return []
        finally:
            cursor.close()

    def execute_model(
        self,
        sql: str,
        table_name: str,
        materialized: str = "view",
        conn=None,
        unique_key: str | None = None,
        incremental_strategy: str = "append",
    ) -> None:
        safe = f"[{table_name}]"
        c = self._ensure_conn(conn)

        if materialized == "materialized_view":
            # SQL Server has indexed views — fall back to table for simplicity
            materialized = "table"

        if materialized == "view":
            self.drop_table(table_name, "view", conn=c)
            self.execute(f"CREATE VIEW {safe} AS {sql}", conn=c)
            return

        if materialized == "ephemeral":
            return

        if materialized == "incremental":
            if self.table_exists(table_name, conn=c):
                if unique_key and incremental_strategy == "merge":
                    # T-SQL MERGE INTO
                    stage = f"#_km_{table_name}"
                    safe_stage = f"[{stage}]"
                    self.execute(f"SELECT * INTO {safe_stage} FROM ({sql}) _src", conn=c)
                    cols_info = self.table_schema(table_name, conn=c)
                    cols = [r["column_name"] for r in cols_info]
                    update_set = ", ".join(
                        f"target.[{col}] = source.[{col}]"
                        for col in cols if col != unique_key
                    )
                    insert_cols = ", ".join(f"[{c}]" for c in cols)
                    insert_vals = ", ".join(f"source.[{c}]" for c in cols)
                    self.execute(f"""
                        MERGE {safe} AS target
                        USING {safe_stage} AS source
                            ON target.[{unique_key}] = source.[{unique_key}]
                        WHEN MATCHED THEN
                            UPDATE SET {update_set}
                        WHEN NOT MATCHED BY TARGET THEN
                            INSERT ({insert_cols}) VALUES ({insert_vals});
                    """, conn=c)
                    self.execute(f"DROP TABLE IF EXISTS {safe_stage}", conn=c)
                else:
                    self.execute(f"INSERT INTO {safe} {sql}", conn=c)
            else:
                self.execute(f"SELECT * INTO {safe} FROM ({sql}) _src", conn=c)
            return

        # table / default: full replace
        self.drop_table(table_name, materialized, conn=c)
        self.execute(f"SELECT * INTO {safe} FROM ({sql}) _src", conn=c)

    def table_exists(self, table_name: str, conn=None) -> bool:
        c = self._ensure_conn(conn)
        result = self.execute(
            "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.TABLES "
            f"WHERE TABLE_NAME = '{table_name.replace(chr(39), chr(39)*2)}'",
            conn=c,
        )
        return bool(result and result[0].get("cnt", 0) > 0)

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        c = self._ensure_conn(conn)
        safe_name = table_name.replace("'", "''")
        rows = self.execute(
            "SELECT COLUMN_NAME AS column_name, DATA_TYPE AS data_type, "
            "IS_NULLABLE AS is_nullable "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_NAME = '{safe_name}' "
            "ORDER BY ORDINAL_POSITION",
            conn=c,
        )
        return rows

    def drop_table(self, table_name: str, materialized: str = "view", conn=None) -> None:
        c = self._ensure_conn(conn)
        safe = f"[{table_name}]"
        if materialized == "view":
            self.execute(f"IF OBJECT_ID(N'{table_name}', N'V') IS NOT NULL DROP VIEW {safe}", conn=c)
        else:
            self.execute(f"IF OBJECT_ID(N'{table_name}', N'U') IS NOT NULL DROP TABLE {safe}", conn=c)

    def execute_snapshot(
        self,
        sql: str,
        table_name: str,
        unique_key: str,
        strategy: str = "timestamp",
        updated_at: str = "updated_at",
        conn=None,
    ) -> None:
        """SCD Type 2 snapshot for SQL Server using T-SQL MERGE."""
        safe = f"[{table_name}]"
        c = self._ensure_conn(conn)
        stage = f"#_km_snap_{table_name}"
        safe_stage = f"[{stage}]"

        try:
            if not self.table_exists(table_name, conn=c):
                self.execute(f"""
                    SELECT *,
                        CONVERT(VARCHAR(64), HASHBYTES('MD5', CAST([{unique_key}] AS NVARCHAR(MAX))), 2) AS _scd_id,
                        GETUTCDATE()               AS _valid_from,
                        CAST(NULL AS DATETIME)     AS _valid_to,
                        CAST(1 AS BIT)             AS _is_current,
                        GETUTCDATE()               AS _dbt_updated_at
                    INTO {safe}
                    FROM ({sql}) _src
                """, conn=c)
                return

            self.execute(f"DROP TABLE IF EXISTS {safe_stage}", conn=c)
            self.execute(f"SELECT * INTO {safe_stage} FROM ({sql}) _src", conn=c)

            if strategy == "timestamp":
                changed_cond = f"n.[{updated_at}] > s._dbt_updated_at"
            else:
                cols_info = self.table_schema(table_name, conn=c)
                audit = {"_scd_id", "_valid_from", "_valid_to", "_is_current", "_dbt_updated_at"}
                check_cols = [
                    r["column_name"] for r in cols_info
                    if r["column_name"] != unique_key and r["column_name"] not in audit
                ]
                changed_cond = (
                    " OR ".join(f"n.[{col}] <> s.[{col}] OR (n.[{col}] IS NULL AND s.[{col}] IS NOT NULL)" for col in check_cols)
                    if check_cols else "1=0"
                )

            # Close current rows
            self.execute(f"""
                UPDATE s SET s._valid_to = GETUTCDATE(), s._is_current = 0
                FROM {safe} s
                JOIN {safe_stage} n ON n.[{unique_key}] = s.[{unique_key}]
                WHERE s._is_current = 1 AND ({changed_cond})
            """, conn=c)

            # Insert new rows
            cols_info = self.table_schema(table_name, conn=c)
            audit_set = {"_scd_id", "_valid_from", "_valid_to", "_is_current", "_dbt_updated_at"}
            src_cols = [r["column_name"] for r in cols_info if r["column_name"] not in audit_set]
            col_list = ", ".join(f"[{c}]" for c in src_cols)
            dbt_ts = f"n.[{updated_at}]" if strategy == "timestamp" else "GETUTCDATE()"

            self.execute(f"""
                INSERT INTO {safe} ({col_list}, _scd_id, _valid_from, _valid_to, _is_current, _dbt_updated_at)
                SELECT {col_list},
                    CONVERT(VARCHAR(64), HASHBYTES('MD5', CAST(n.[{unique_key}] AS NVARCHAR(MAX))), 2),
                    GETUTCDATE(), NULL, 1, {dbt_ts}
                FROM {safe_stage} n
                WHERE NOT EXISTS (
                    SELECT 1 FROM {safe} s
                    WHERE s.[{unique_key}] = n.[{unique_key}] AND s._is_current = 1
                )
            """, conn=c)

            self.execute(f"DROP TABLE IF EXISTS {safe_stage}", conn=c)
        except Exception:
            try:
                self.execute(f"DROP TABLE IF EXISTS {safe_stage}", conn=c)
            except Exception:
                pass
            raise
