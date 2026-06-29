"""ClickHouse adapter for KelpMesh.

Install the driver:
    pip install kelpmesh[clickhouse]

kelpmesh.yml:
    warehouse:
      type: clickhouse
      host: localhost
      port: 8123
      database: default
      user: default
      password: ""

ClickHouse notes:
  - No MERGE/UPSERT statement — incremental uses ReplacingMergeTree engine with OPTIMIZE FINAL
  - Snapshots use a manual SCD2 pattern with sign/version columns
  - Views are created with CREATE OR REPLACE VIEW
  - Tables use MergeTree engine family by default
"""

from kelpmesh.adapters.base import WarehouseAdapter
from kelpmesh.core.config import WarehouseConfig


class ClickHouseAdapter(WarehouseAdapter):
    def __init__(self, config: WarehouseConfig) -> None:
        self.config = config
        self._client = None

    def connect(self) -> None:
        try:
            import clickhouse_driver
        except ImportError:
            raise ImportError(
                "ClickHouse driver not installed. Run: pip install kelpmesh[clickhouse]"
            )
        self._client = clickhouse_driver.Client(
            host=self.config.host or "localhost",
            port=self.config.port or 9000,
            database=self.config.database or "default",
            user=self.config.user or "default",
            password=self.config.password or "",
            settings={"use_numpy": False},
        )
        # Verify connectivity
        self._client.execute("SELECT 1")

    def disconnect(self) -> None:
        if self._client:
            self._client.disconnect()
            self._client = None

    def _ensure_client(self):
        if not self._client:
            self.connect()
        return self._client

    def execute(self, sql: str, conn=None) -> list[dict]:
        client = self._ensure_client()
        try:
            rows, columns = client.execute(sql, with_column_types=True)
            if not columns:
                return []
            col_names = [c[0] for c in columns]
            return [dict(zip(col_names, row)) for row in rows]
        except Exception as e:
            raise RuntimeError(f"ClickHouse execute error: {e}") from e

    def execute_model(
        self,
        sql: str,
        table_name: str,
        materialized: str = "view",
        conn=None,
        unique_key: str | None = None,
        incremental_strategy: str = "append",
    ) -> None:
        client = self._ensure_client()
        safe = f"`{table_name}`"
        db = self.config.database or "default"

        if materialized == "view":
            client.execute(f"DROP VIEW IF EXISTS {safe}")
            client.execute(f"CREATE VIEW {safe} AS {sql}")
            return

        if materialized == "ephemeral":
            return

        if materialized == "incremental":
            exists = self.table_exists(table_name)
            if not exists:
                # Create with ReplacingMergeTree when unique_key is provided
                if unique_key:
                    client.execute(
                        f"CREATE TABLE {safe} ENGINE = ReplacingMergeTree() "
                        f"ORDER BY {unique_key} AS {sql}"
                    )
                else:
                    client.execute(
                        f"CREATE TABLE {safe} ENGINE = MergeTree() "
                        f"ORDER BY tuple() AS {sql}"
                    )
            else:
                if unique_key and incremental_strategy == "merge":
                    # ClickHouse: insert all, then OPTIMIZE to deduplicate
                    client.execute(f"INSERT INTO {safe} {sql}")
                    client.execute(f"OPTIMIZE TABLE {safe} FINAL")
                else:
                    # Append-only
                    client.execute(f"INSERT INTO {safe} {sql}")
            return

        # table / snapshot / default: full replace
        self.drop_table(table_name, materialized)
        client.execute(
            f"CREATE TABLE {safe} ENGINE = MergeTree() "
            f"ORDER BY tuple() AS {sql}"
        )

    def table_exists(self, table_name: str, conn=None) -> bool:
        client = self._ensure_client()
        db = self.config.database or "default"
        rows, _ = client.execute(
            "SELECT count() FROM system.tables "
            "WHERE database = %(db)s AND name = %(tbl)s",
            {"db": db, "tbl": table_name},
            with_column_types=True,
        )
        return bool(rows and rows[0][0] > 0)

    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        client = self._ensure_client()
        db = self.config.database or "default"
        rows, cols = client.execute(
            "SELECT name, type, is_in_primary_key "
            "FROM system.columns "
            "WHERE database = %(db)s AND table = %(tbl)s "
            "ORDER BY position",
            {"db": db, "tbl": table_name},
            with_column_types=True,
        )
        col_names = [c[0] for c in cols]
        result = []
        for row in rows:
            r = dict(zip(col_names, row))
            result.append({
                "column_name": r["name"],
                "data_type": r["type"],
                "is_nullable": "YES",
            })
        return result

    def drop_table(self, table_name: str, materialized: str = "view", conn=None) -> None:
        client = self._ensure_client()
        safe = f"`{table_name}`"
        if materialized == "view":
            client.execute(f"DROP VIEW IF EXISTS {safe}")
        else:
            client.execute(f"DROP TABLE IF EXISTS {safe}")

    def preview(self, sql: str, limit: int = 100, conn=None) -> list[dict]:
        return self.execute(f"SELECT * FROM ({sql}) AS _km_preview LIMIT {limit}")

    def fetch_row_count(self, table_name: str, conn=None) -> int:
        result = self.execute(f"SELECT count() AS cnt FROM `{table_name}`")
        return result[0]["cnt"] if result else 0

    def load_csv(self, path: str, table_name: str, delimiter: str = ",") -> None:
        """Load CSV via pandas INSERT for ClickHouse."""
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas required for CSV loading: pip install pandas")
        df = pd.read_csv(path, sep=delimiter)
        client = self._ensure_client()
        safe = f"`{table_name}`"
        # Create table from schema
        col_defs = ", ".join(f"`{c}` String" for c in df.columns)
        client.execute(
            f"CREATE TABLE IF NOT EXISTS {safe} ({col_defs}) "
            f"ENGINE = MergeTree() ORDER BY tuple()"
        )
        # Insert rows as batches
        records = df.to_dict("records")
        if records:
            cols = list(df.columns)
            col_list = ", ".join(f"`{c}`" for c in cols)
            rows = [tuple(str(r[c]) for c in cols) for r in records]
            client.execute(f"INSERT INTO {safe} ({col_list}) VALUES", rows)

    def execute_snapshot(
        self,
        sql: str,
        table_name: str,
        unique_key: str,
        strategy: str = "timestamp",
        updated_at: str = "updated_at",
        conn=None,
    ) -> None:
        """SCD Type 2 snapshot for ClickHouse using sign/version pattern."""
        client = self._ensure_client()
        safe = f"`{table_name}`"
        uk = unique_key

        if not self.table_exists(table_name):
            client.execute(
                f"CREATE TABLE {safe} "
                f"ENGINE = CollapsingMergeTree(_scd_sign) "
                f"ORDER BY ({uk}, _valid_from) AS "
                f"SELECT *, "
                f"  cityHash64(toString({uk})) AS _scd_id, "
                f"  now()                       AS _valid_from, "
                f"  toDateTime('9999-12-31')    AS _valid_to, "
                f"  1                           AS _is_current, "
                f"  1                           AS _scd_sign, "
                f"  now()                       AS _dbt_updated_at "
                f"FROM ({sql}) _src"
            )
            return

        stage = f"_km_snap_{table_name}"
        safe_stage = f"`{stage}`"

        try:
            client.execute(f"DROP TABLE IF EXISTS {safe_stage}")
            client.execute(
                f"CREATE TABLE {safe_stage} ENGINE = MergeTree() "
                f"ORDER BY tuple() AS {sql}"
            )

            if strategy == "timestamp":
                changed_cond = f"n.{updated_at} > s._dbt_updated_at"
            else:
                cols_info = self.table_schema(table_name)
                audit = {"_scd_id", "_valid_from", "_valid_to", "_is_current", "_scd_sign", "_dbt_updated_at"}
                check_cols = [
                    c["column_name"] for c in cols_info
                    if c["column_name"] != uk and c["column_name"] not in audit
                ]
                changed_cond = (
                    " OR ".join(f"n.`{col}` != s.`{col}`" for col in check_cols)
                    if check_cols else "1=0"
                )

            # Insert tombstone rows for changed current records
            client.execute(f"""
                INSERT INTO {safe}
                SELECT s.* EXCEPT (_scd_sign), -1 AS _scd_sign
                FROM {safe} s
                JOIN {safe_stage} n ON n.`{uk}` = s.`{uk}`
                WHERE s._is_current = 1 AND ({changed_cond})
            """)

            # Insert new versions
            client.execute(f"""
                INSERT INTO {safe}
                SELECT n.*,
                    cityHash64(toString(n.`{uk}`)) AS _scd_id,
                    now()                           AS _valid_from,
                    toDateTime('9999-12-31')        AS _valid_to,
                    1                               AS _is_current,
                    1                               AS _scd_sign,
                    now()                           AS _dbt_updated_at
                FROM {safe_stage} n
                WHERE NOT EXISTS (
                    SELECT 1 FROM {safe} s
                    WHERE s.`{uk}` = n.`{uk}` AND s._is_current = 1
                )
            """)

            client.execute(f"OPTIMIZE TABLE {safe} FINAL")
            client.execute(f"DROP TABLE IF EXISTS {safe_stage}")
        except Exception:
            client.execute(f"DROP TABLE IF EXISTS {safe_stage}")
            raise
