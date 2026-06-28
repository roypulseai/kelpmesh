"""Trino / Presto adapter for KelpMesh.

Install the driver:
    pip install kelpmesh[trino]

kelpmesh.yml:
    warehouse:
      type: trino
      host: trino.example.com
      port: 8080
      database: hive          # Trino catalog
      schema: default         # Trino schema
      user: trino
      # For HTTPS with authentication:
      # extra:
      #   http_scheme: https
      #   auth_type: jwt          # or basic, ldap, kerberos, certificate
      #   access_token: "{{ env_var('TRINO_TOKEN') }}"
"""

from kelpmesh.adapters.base import WarehouseAdapter
from kelpmesh.core.config import WarehouseConfig


class TrinoAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig) -> None:
        self.config = config
        self.conn = None

    def connect(self) -> None:
        try:
            import trino
        except ImportError:
            raise ImportError(
                "Trino driver not installed. Run: pip install kelpmesh[trino]"
            )
        extra = getattr(self.config, "extra", {}) or {}
        http_scheme = extra.get("http_scheme", "http")
        auth = None

        auth_type = extra.get("auth_type", "")
        if auth_type == "jwt":
            token = extra.get("access_token", "")
            auth = trino.auth.JWTAuthentication(token)
        elif auth_type in ("basic", "ldap"):
            auth = trino.auth.BasicAuthentication(
                self.config.user, self.config.password or ""
            )

        self.conn = trino.dbapi.connect(
            host=self.config.host,
            port=self.config.port or 8080,
            user=self.config.user,
            catalog=self.config.database or "hive",
            schema=getattr(self.config, "schema", "default") or "default",
            http_scheme=http_scheme,
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
        self, sql: str, table_name: str, materialized: str = "view",
        conn=None, unique_key: str | None = None,
        incremental_strategy: str = "append",
    ) -> None:
        # Trino uses fully-qualified names: catalog.schema.table
        # table_name may already be fully qualified
        safe = f'"{table_name}"'
        c = self._ensure_conn(conn)

        if materialized == "incremental":
            if self.table_exists(table_name, conn=c):
                if unique_key and incremental_strategy == "merge":
                    # Trino MERGE (available since Trino 393)
                    temp = f"_km_merge_{table_name.replace('.', '_')}"
                    self.execute(f"CREATE TABLE {temp} AS {sql}", conn=c)
                    cols_info = self.table_schema(table_name, conn=c)
                    cols = [r["column_name"] for r in cols_info]
                    update_set = ", ".join(
                        f't."{col}" = s."{col}"'
                        for col in cols if col != unique_key
                    )
                    self.execute(f"""
                        MERGE INTO {safe} t
                        USING {temp} s ON t."{unique_key}" = s."{unique_key}"
                        WHEN MATCHED THEN UPDATE SET {update_set}
                        WHEN NOT MATCHED THEN INSERT VALUES ({', '.join(f's."{c}"' for c in cols)})
                    """, conn=c)
                    self.execute(f'DROP TABLE IF EXISTS "{temp}"', conn=c)
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
        # table_name may be catalog.schema.table — extract parts
        parts = table_name.split(".")
        if len(parts) == 3:
            catalog, schema, tbl = parts
        elif len(parts) == 2:
            schema, tbl = parts
            catalog = None
        else:
            tbl = table_name
            schema = None
            catalog = None

        c = self._ensure_conn(conn)
        where = "table_name = ?1"
        params: list = [tbl]
        if schema:
            where += " AND table_schema = ?2"
            params.append(schema)
        if catalog:
            where += " AND table_catalog = ?3"
            params.append(catalog)

        cursor = c.cursor()
        try:
            cursor.execute(
                f"SELECT COUNT(*) FROM information_schema.tables WHERE {where}",
                params,
            )
            return cursor.fetchone()[0] > 0
        finally:
            cursor.close()

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        parts = table_name.split(".")
        tbl = parts[-1]
        schema = parts[-2] if len(parts) >= 2 else None
        c = self._ensure_conn(conn)
        cursor = c.cursor()
        try:
            where = "table_name = ?"
            params: list = [tbl]
            if schema:
                where += " AND table_schema = ?"
                params.append(schema)
            cursor.execute(
                f"SELECT column_name, data_type, is_nullable "
                f"FROM information_schema.columns WHERE {where} "
                f"ORDER BY ordinal_position",
                params,
            )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def drop_table(self, table_name: str, materialized: str = "view", conn=None) -> None:
        safe = f'"{table_name}"'
        c = self._ensure_conn(conn)
        if materialized == "view":
            self.execute(f"DROP VIEW IF EXISTS {safe}", conn=c)
        else:
            self.execute(f"DROP TABLE IF EXISTS {safe}", conn=c)

    def execute_snapshot(
        self, sql: str, table_name: str, unique_key: str,
        strategy: str = "timestamp", updated_at: str = "updated_at", conn=None,
    ) -> None:
        """SCD Type 2 snapshot for Trino."""
        safe = f'"{table_name}"'
        uk = unique_key
        c = self._ensure_conn(conn)

        if not self.table_exists(table_name, conn=c):
            dbt_updated_expr = f'"{updated_at}"' if strategy == "timestamp" else "CURRENT_TIMESTAMP"
            self.execute(f"""
                CREATE TABLE {safe} AS
                SELECT *,
                    to_hex(md5(to_utf8(CAST("{uk}" AS VARCHAR))) ) AS _scd_id,
                    CURRENT_TIMESTAMP                               AS _valid_from,
                    CAST(NULL AS TIMESTAMP)                         AS _valid_to,
                    TRUE                                            AS _is_current,
                    {dbt_updated_expr}                             AS _dbt_updated_at
                FROM ({sql}) _src
            """, conn=c)
            return

        stage = f"_km_snap_{table_name.replace('.', '_')}"
        self.execute(f'DROP TABLE IF EXISTS "{stage}"', conn=c)
        self.execute(f'CREATE TABLE "{stage}" AS {sql}', conn=c)

        if strategy == "timestamp":
            changed_cond = f'n."{updated_at}" > s._dbt_updated_at'
        else:
            cols_info = self.table_schema(table_name, conn=c)
            audit = {"_scd_id", "_valid_from", "_valid_to", "_is_current", "_dbt_updated_at"}
            check_cols = [
                r["column_name"] for r in cols_info
                if r["column_name"] != uk and r["column_name"] not in audit
            ]
            changed_cond = (
                " OR ".join(f'n."{col}" IS DISTINCT FROM s."{col}"' for col in check_cols)
                if check_cols else "FALSE"
            )

        cols_info = self.table_schema(table_name, conn=c)
        audit = {"_scd_id", "_valid_from", "_valid_to", "_is_current", "_dbt_updated_at"}
        src_cols = [r["column_name"] for r in cols_info if r["column_name"] not in audit]

        # Trino MERGE
        update_set = "_valid_to = CURRENT_TIMESTAMP, _is_current = FALSE"
        col_insert = ", ".join(f'"{c}"' for c in src_cols)
        dbt_updated_insert = f'n."{updated_at}"' if strategy == "timestamp" else "CURRENT_TIMESTAMP"

        self.execute(f"""
            MERGE INTO {safe} t
            USING "{stage}" n ON t."{uk}" = n."{uk}" AND t._is_current = TRUE
            WHEN MATCHED AND ({changed_cond}) THEN UPDATE SET {update_set}
            WHEN NOT MATCHED THEN INSERT ({col_insert}, _scd_id, _valid_from, _valid_to, _is_current, _dbt_updated_at)
            VALUES ({', '.join(f'n."{c}"' for c in src_cols)},
                    to_hex(md5(to_utf8(CAST(n."{uk}" AS VARCHAR)))),
                    CURRENT_TIMESTAMP, NULL, TRUE, {dbt_updated_insert})
        """, conn=c)

        self.execute(f'DROP TABLE IF EXISTS "{stage}"', conn=c)
