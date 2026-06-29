"""Microsoft Fabric adapter — connects via SQL Analytics endpoint (T-SQL over ODBC)."""

import logging
from kelpmesh.adapters.base import WarehouseAdapter, sanitize_name
from kelpmesh.core.config import WarehouseConfig

_logger = logging.getLogger(__name__)

_FABRIC_SCOPE = "https://database.windows.net//.default"

# T-SQL uses square-bracket quoting; re-quote identifiers accordingly.
def _tsql_name(name: str) -> str:
    return f"[{name.strip('[]')}]"


class FabricAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig):
        self.config = config
        self.conn = None

    def connect(self):
        import pyodbc

        if self.config.connection_string:
            conn_str = self.config.connection_string
        else:
            token = self._acquire_token()
            server = self.config.account
            database = self.config.database
            if not server or not database:
                raise ValueError(
                    "Fabric adapter requires 'account' (server hostname) and 'database', "
                    "or a full 'connection_string'."
                )
            conn_str = (
                f"Driver={{ODBC Driver 18 for SQL Server}};"
                f"Server=tcp:{server},1433;"
                f"Database={database};"
                f"Encrypt=yes;"
                f"TrustServerCertificate=no;"
            )
            self.conn = pyodbc.connect(conn_str, attrs_before={1256: token})
            return

        self.conn = pyodbc.connect(conn_str)

    def _acquire_token(self) -> str:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
        token = credential.get_token(_FABRIC_SCOPE)
        return token.token

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
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            return []

    def execute_model(
        self, sql: str, table_name: str, materialized: str = "view",
        conn=None, unique_key: str | None = None,
        incremental_strategy: str = "append",
    ):
        safe = _tsql_name(table_name)
        c = self._ensure_conn(conn)

        if materialized == "incremental":
            if self.table_exists(table_name, conn=c):
                if unique_key and incremental_strategy == "merge":
                    with c.cursor() as cur:
                        # Get column names via TOP 0 subquery
                        cur.execute(f"SELECT TOP 0 * FROM ({sql}) AS _km_src")
                        cols = [desc[0] for desc in cur.description]
                    col_list = ", ".join(_tsql_name(col) for col in cols)
                    source_vals = ", ".join(f"source.{_tsql_name(col)}" for col in cols)
                    update_set = ", ".join(
                        f"target.{_tsql_name(col)} = source.{_tsql_name(col)}"
                        for col in cols if col != unique_key
                    )
                    uk = _tsql_name(unique_key)
                    merge_sql = f"""
                        MERGE INTO {safe} AS target
                        USING ({sql}) AS source
                        ON target.{uk} = source.{uk}
                        WHEN MATCHED THEN UPDATE SET {update_set}
                        WHEN NOT MATCHED THEN INSERT ({col_list}) VALUES ({source_vals});
                    """
                    with c.cursor() as cur:
                        cur.execute(merge_sql)
                else:
                    with c.cursor() as cur:
                        cur.execute(f"INSERT INTO {safe} {sql}")
            else:
                # T-SQL: CREATE TABLE AS SELECT is not valid; use SELECT INTO
                with c.cursor() as cur:
                    cur.execute(f"SELECT * INTO {safe} FROM ({sql}) AS _km_src")
            return

        self.drop_table(table_name, materialized, conn=c)
        with c.cursor() as cur:
            if materialized == "table":
                # T-SQL: SELECT * INTO instead of CREATE TABLE AS
                cur.execute(f"SELECT * INTO {safe} FROM ({sql}) AS _km_src")
            elif materialized == "ephemeral":
                pass
            else:
                cur.execute(f"CREATE VIEW {safe} AS {sql}")

    def table_exists(self, table_name: str, conn=None) -> bool:
        c = self._ensure_conn(conn)
        with c.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                (table_name,),
            )
            row = cur.fetchone()
            return row[0] > 0 if row else False

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        c = self._ensure_conn(conn)
        with c.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = ?",
                (table_name,),
            )
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def drop_table(self, table_name: str, materialized: str = "view", conn=None):
        safe = _tsql_name(table_name)
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
        """SCD Type 2 snapshot execution (T-SQL / Microsoft Fabric)."""
        safe = _tsql_name(table_name)
        uk = _tsql_name(unique_key)
        stage = f"#_km_snap_{table_name}"
        c = self._ensure_conn(conn)

        if not self.table_exists(table_name, conn=c):
            dbt_updated_expr = (
                f'CAST({_tsql_name(updated_at)} AS DATETIME2)'
                if strategy == "timestamp"
                else "GETDATE()"
            )
            with c.cursor() as cur:
                cur.execute(f"""
                    SELECT *,
                        CAST(HASHBYTES('MD5', CAST({uk} AS NVARCHAR(MAX))) AS VARCHAR(MAX)) AS _scd_id,
                        GETDATE()          AS _valid_from,
                        CAST(NULL AS DATETIME2) AS _valid_to,
                        CAST(1 AS BIT)     AS _is_current,
                        {dbt_updated_expr} AS _dbt_updated_at
                    INTO {safe}
                    FROM ({sql}) AS _src
                """)
            return

        with c.cursor() as cur:
            cur.execute(f"SELECT * INTO {stage} FROM ({sql}) AS _src")

        if strategy == "timestamp":
            changed_cond = f'CAST(n.{_tsql_name(updated_at)} AS DATETIME2) > s._dbt_updated_at'
        else:
            with c.cursor() as cur:
                cur.execute(f"SELECT TOP 0 * FROM {stage}")
                cols = [desc[0] for desc in cur.description]
            check_cols = [col for col in cols if col != unique_key]
            if check_cols:
                changed_cond = " OR ".join(
                    f't.{_tsql_name(col)} <> n.{_tsql_name(col)}'
                    for col in check_cols
                )
            else:
                changed_cond = "1=0"

        with c.cursor() as cur:
            cur.execute(f"""
                UPDATE t
                SET _valid_to = GETDATE(), _is_current = 0
                FROM {safe} t
                INNER JOIN {stage} n ON t.{uk} = n.{uk}
                WHERE t._is_current = 1 AND ({changed_cond})
            """)

        dbt_updated_insert = (
            f'CAST(n.{_tsql_name(updated_at)} AS DATETIME2)'
            if strategy == "timestamp"
            else "GETDATE()"
        )
        with c.cursor() as cur:
            cur.execute(f"""
                INSERT INTO {safe}
                SELECT n.*,
                    CAST(HASHBYTES('MD5', CAST(n.{uk} AS NVARCHAR(MAX))) AS VARCHAR(MAX)) AS _scd_id,
                    GETDATE()              AS _valid_from,
                    CAST(NULL AS DATETIME2) AS _valid_to,
                    CAST(1 AS BIT)         AS _is_current,
                    {dbt_updated_insert}   AS _dbt_updated_at
                FROM {stage} n
                WHERE NOT EXISTS (
                    SELECT 1 FROM {safe} s
                    WHERE s.{uk} = n.{uk} AND s._is_current = 1
                )
            """)
