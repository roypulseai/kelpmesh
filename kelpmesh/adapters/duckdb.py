import os
import threading

import duckdb

from kelpmesh.adapters.base import WarehouseAdapter, sanitize_name
from kelpmesh.core.config import WarehouseConfig


def _encryption_config(config: WarehouseConfig) -> dict:
    """DuckDB open-source does not support native connect-time encryption.
    File-level encryption is handled by kelpmesh.core.crypto (encrypt/decrypt
    the .duckdb file before/after use). Return empty dict always."""
    return {}


class ConnectionPool:
    def __init__(self, db_path: str, size: int = 4, encryption_key: str | None = None):
        self._conns: list[duckdb.DuckDBPyConnection] = []
        self._lock = threading.Lock()
        self._available = threading.Semaphore(size)
        self._db_path = db_path
        self._closed = False
        for _ in range(size):
            conn = duckdb.connect(db_path)
            self._conns.append(conn)

    def acquire(self) -> duckdb.DuckDBPyConnection:
        self._available.acquire()
        with self._lock:
            if self._closed:
                self._available.release()
                raise RuntimeError("Connection pool is closed")
            return self._conns.pop()

    def release(self, conn: duckdb.DuckDBPyConnection) -> None:
        try:
            if self._closed:
                conn.close()
                return
            with self._lock:
                self._conns.append(conn)
        finally:
            self._available.release()

    def close_all(self) -> None:
        self._closed = True
        with self._lock:
            for conn in self._conns:
                conn.close()
            self._conns.clear()


class DuckDBAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig | None = None, project_path: str | None = None):
        self.config = config or WarehouseConfig(type="duckdb", path=":memory:")
        self.project_path = project_path
        self.conn: duckdb.DuckDBPyConnection | None = None
        self._pool: ConnectionPool | None = None
        self._encryption_key = self.config.encryption_key or os.environ.get("KELPMESH_ENCRYPTION_KEY")

    def _get_db_path(self) -> str:
        path = self.config.path or ":memory:"
        if path != ":memory:" and self.project_path:
            path = os.path.join(self.project_path, path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def connect(self):
        if self.conn:
            return
        path = self._get_db_path()
        connect_kwargs = _encryption_config(self.config)
        self.conn = duckdb.connect(path, **connect_kwargs)
        if self.config.database:
            self.conn.execute(f"USE {self.config.database}")

    def init_pool(self, size: int = 4):
        if self._pool:
            return
        path = self._get_db_path()
        if path == ":memory:":
            # Pooling is useless for in-memory — each connection is isolated.
            self.connect()
            return
        self._pool = ConnectionPool(path, size=size, encryption_key=self._encryption_key)

    def acquire_conn(self) -> duckdb.DuckDBPyConnection:
        if self._pool:
            return self._pool.acquire()
        if not self.conn:
            self.connect()
        return self.conn

    def release_conn(self, conn: duckdb.DuckDBPyConnection) -> None:
        if self._pool:
            self._pool.release(conn)

    def disconnect(self):
        if self._pool:
            self._pool.close_all()
            self._pool = None
        if self.conn:
            self.conn.close()
            self.conn = None

    def execute(
        self, sql: str, conn: duckdb.DuckDBPyConnection | None = None
    ) -> list[dict]:
        c = conn or self.acquire_conn()
        try:
            result = c.execute(sql)
            if result.description:
                columns = [desc[0] for desc in result.description]
                rows = result.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            return []
        finally:
            if conn is None:
                self.release_conn(c)

    def execute_model(
        self,
        sql: str,
        table_name: str,
        materialized: str = "view",
        conn: duckdb.DuckDBPyConnection | None = None,
        unique_key: str | None = None,
        incremental_strategy: str = "append",
    ):
        c = conn or self.acquire_conn()
        safe = sanitize_name(table_name)
        try:
            if materialized == "incremental" and self.table_exists(table_name, conn=c):
                if unique_key and incremental_strategy == "merge":
                    temp_table = f"{table_name}_km_merge"
                    safe_temp = sanitize_name(temp_table)
                    c.execute(f'CREATE TABLE {safe_temp} AS {sql}')
                    cols = [desc[0] for desc in c.execute(f'SELECT * FROM {safe_temp} LIMIT 0').description]
                    col_list = ", ".join(f'"{col}"' for col in cols)
                    update_set = ", ".join(f'"{col}" = EXCLUDED."{col}"' for col in cols)
                    c.execute(f"""
                        INSERT INTO {safe} ({col_list})
                        SELECT {col_list} FROM {safe_temp}
                        ON CONFLICT ("{unique_key}") DO UPDATE SET {update_set}
                    """)
                    c.execute(f'DROP TABLE {safe_temp}')
                else:
                    c.execute(f'INSERT INTO {safe} {sql}')
            elif materialized == "incremental":
                c.execute(f'CREATE TABLE {safe} AS {sql}')
            else:
                self.drop_table(table_name, materialized, conn=c)
                if materialized == "table":
                    c.execute(f'CREATE TABLE {safe} AS {sql}')
                elif materialized == "ephemeral":
                    pass
                else:
                    c.execute(f'CREATE OR REPLACE VIEW {safe} AS {sql}')
        finally:
            if conn is None:
                self.release_conn(c)

    def table_exists(
        self, table_name: str, conn: duckdb.DuckDBPyConnection | None = None
    ) -> bool:
        c = conn or self.acquire_conn()
        try:
            result = c.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                [table_name],
            ).fetchone()
            return result[0] > 0
        finally:
            if conn is None:
                self.release_conn(c)

    def table_schema(
        self, table_name: str, conn: duckdb.DuckDBPyConnection | None = None
    ) -> list[dict]:
        c = conn or self.acquire_conn()
        try:
            result = c.execute(
                """SELECT column_name, data_type, is_nullable
                   FROM information_schema.columns
                   WHERE table_name = ?""",
                [table_name],
            )
            columns = [desc[0] for desc in result.description]
            return [dict(zip(columns, row)) for row in result.fetchall()]
        finally:
            if conn is None:
                self.release_conn(c)

    def drop_table(
        self,
        table_name: str,
        materialized: str = "view",
        conn: duckdb.DuckDBPyConnection | None = None,
    ):
        safe = sanitize_name(table_name)
        c = conn or self.acquire_conn()
        try:
            if materialized == "view":
                c.execute(f"DROP VIEW IF EXISTS {safe}")
            else:
                c.execute(f"DROP TABLE IF EXISTS {safe}")
        finally:
            if conn is None:
                self.release_conn(c)

    def fetch_row_count(
        self, table_name: str, conn: duckdb.DuckDBPyConnection | None = None
    ) -> int:
        safe = sanitize_name(table_name)
        c = conn or self.acquire_conn()
        try:
            result = c.execute(
                f"SELECT COUNT(*) AS cnt FROM {safe}"
            ).fetchone()
            return result[0] if result else 0
        finally:
            if conn is None:
                self.release_conn(c)

    def execute_snapshot(
        self,
        sql: str,
        table_name: str,
        unique_key: str,
        strategy: str = "timestamp",
        updated_at: str = "updated_at",
        conn: "duckdb.DuckDBPyConnection | None" = None,
    ) -> None:
        """SCD Type 2 snapshot execution."""
        from kelpmesh.adapters.base import sanitize_name
        c = conn or self.acquire_conn()
        safe = sanitize_name(table_name)
        safe_uk = sanitize_name(unique_key)
        try:
            safe_ua = sanitize_name(updated_at)
            if not self.table_exists(table_name, conn=c):
                dbt_updated_expr = (
                    f"CAST({safe_ua} AS TIMESTAMP)"
                    if strategy == "timestamp"
                    else "LOCALTIMESTAMP"
                )
                c.execute(f"""
                    CREATE TABLE {safe} AS
                    SELECT *,
                        md5(CAST({safe_uk} AS VARCHAR)) AS _scd_id,
                        LOCALTIMESTAMP                   AS _valid_from,
                        NULL::TIMESTAMP                  AS _valid_to,
                        TRUE                             AS _is_current,
                        {dbt_updated_expr}               AS _dbt_updated_at
                    FROM ({sql}) _snap_src
                """)
                return

            tmp = f"_km_snap_{table_name}_new"
            safe_tmp = sanitize_name(tmp)
            c.execute(f"DROP TABLE IF EXISTS {safe_tmp}")
            c.execute(f"CREATE TEMP TABLE {safe_tmp} AS SELECT * FROM ({sql}) _snap_src")

            if strategy == "timestamp":
                changed_filter = f"CAST(n.{safe_ua} AS TIMESTAMP) > s._dbt_updated_at"
            else:
                # check strategy — any column change
                cols = [
                    d[0] for d in
                    c.execute(f"SELECT * FROM {safe_tmp} LIMIT 0").description
                ]
                check_cols = [col for col in cols if col != unique_key]
                if check_cols:
                    changed_filter = " OR ".join(
                        f"n.{sanitize_name(col)} IS DISTINCT FROM s.{sanitize_name(col)}"
                        for col in check_cols
                    )
                else:
                    changed_filter = "FALSE"

            # Expire changed records
            c.execute(f"""
                UPDATE {safe} SET _valid_to = LOCALTIMESTAMP, _is_current = FALSE
                WHERE {safe_uk} IN (
                    SELECT n.{safe_uk} FROM {safe_tmp} n
                    JOIN {safe} s ON n.{safe_uk} = s.{safe_uk}
                    WHERE s._is_current AND ({changed_filter})
                )
                AND _is_current
            """)

            # Insert new + changed records
            insert_dbt_updated = (
                f"CAST(n.{safe_ua} AS TIMESTAMP)"
                if strategy == "timestamp"
                else "LOCALTIMESTAMP"
            )
            c.execute(f"""
                INSERT INTO {safe}
                SELECT n.*,
                    md5(CAST(n.{safe_uk} AS VARCHAR)) AS _scd_id,
                    LOCALTIMESTAMP                     AS _valid_from,
                    NULL::TIMESTAMP                    AS _valid_to,
                    TRUE                               AS _is_current,
                    {insert_dbt_updated}               AS _dbt_updated_at
                FROM {safe_tmp} n
                WHERE NOT EXISTS (
                    SELECT 1 FROM {safe} s
                    WHERE s.{safe_uk} = n.{safe_uk} AND s._is_current
                )
            """)

            c.execute(f"DROP TABLE IF EXISTS {safe_tmp}")
        finally:
            if conn is None:
                self.release_conn(c)

    def load_csv(
        self,
        path: str,
        table_name: str,
        delimiter: str = ",",
        conn: duckdb.DuckDBPyConnection | None = None,
    ) -> None:
        safe = sanitize_name(table_name)
        c = conn or self.acquire_conn()
        try:
            c.execute(f"CREATE OR REPLACE TABLE {safe} AS SELECT * FROM read_csv_auto('{path}', delim='{delimiter}', header=true)")
        finally:
            if conn is None:
                self.release_conn(c)
