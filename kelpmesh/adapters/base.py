import re
from abc import ABC, abstractmethod
from typing import Any

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def sanitize_name(name: str) -> str:
    """Validate and quote a SQL identifier to prevent injection."""
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{name}"'


class WarehouseAdapter(ABC):
    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def execute(self, sql: str, conn=None) -> Any:
        ...

    @abstractmethod
    def execute_model(
        self, sql: str, table_name: str, materialized: str = "view",
        conn=None, unique_key: str | None = None,
        incremental_strategy: str = "append",
    ) -> None:
        ...

    @abstractmethod
    def table_exists(self, table_name: str, conn=None) -> bool:
        ...

    @abstractmethod
    def table_schema(self, table_name: str, conn=None) -> list[dict]:
        ...

    @abstractmethod
    def drop_table(self, table_name: str, materialized: str = "view", conn=None) -> None:
        ...

    def acquire_conn(self) -> Any:
        return None

    def release_conn(self, conn: Any) -> None:
        pass

    def preview(self, sql: str, limit: int = 100, conn=None) -> list[dict]:
        wrapped = f"SELECT * FROM ({sql}) AS _km_preview LIMIT {limit}"
        return self.execute(wrapped, conn=conn)

    def fetch_row_count(self, table_name: str, conn=None) -> int:
        result = self.execute(f"SELECT COUNT(*) AS cnt FROM {table_name}", conn=conn)
        if result and len(result) > 0:
            return result[0]["cnt"]
        return 0

    def load_csv(self, path: str, table_name: str, delimiter: str = ",") -> None:
        """Load a CSV/TSV file into a table. Override for warehouse-native ingest."""
        import pandas as pd
        df = pd.read_csv(path, sep=delimiter)
        self._write_df(df, table_name)

    def execute_snapshot(
        self,
        sql: str,
        table_name: str,
        unique_key: str,
        strategy: str = "timestamp",
        updated_at: str = "updated_at",
        conn=None,
    ) -> None:
        """SCD Type 2 snapshot. Override per adapter."""
        raise NotImplementedError(
            f"Snapshots are not yet implemented for {self.__class__.__name__}. "
            f"Supported: DuckDB, Postgres, Snowflake, BigQuery, Databricks, Fabric, Redshift."
        )

    def execute_materialized_view(
        self,
        sql: str,
        table_name: str,
        conn=None,
    ) -> None:
        """Create or refresh a materialized view. Falls back to table if unsupported."""
        # Default: fall back to regular table (DuckDB, MySQL, Hive don't support MV natively)
        self.drop_table(table_name, materialized="table", conn=conn)
        self.execute_model(sql, table_name, materialized="table", conn=conn)

    def _write_df(self, df, table_name: str) -> None:
        """Write a pandas DataFrame to the warehouse as a table."""
        from io import StringIO
        buf = StringIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        lines = []
        for _ in range(20):
            line = buf.readline()
            if not line:
                break
            lines.append(line.strip())
        header = lines[0].split(",") if lines else []
        sample = []
        for line in lines[1:]:
            vals = line.split(",")
            if len(vals) == len(header):
                sample.append(vals)
        import re
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", table_name)
        col_defs = ", ".join(
            f'"{c}" VARCHAR' for c in header
        )
        stmt = f"CREATE TABLE IF NOT EXISTS \"{clean}\" ({col_defs})"
        self.execute(stmt)
        placeholders = ", ".join("?" for _ in header)
        insert = f'INSERT INTO "{clean}" VALUES ({placeholders})'
        for row in sample:
            self.execute(insert, list(row))
        # Rest via chunked INSERT from buffered CSV
        buf.seek(0)
        next(buf)  # skip header
        chunk = []
        for line in buf:
            vals = line.strip().split(",")
            if len(vals) == len(header):
                chunk.append(vals)
            if len(chunk) >= 500:
                for row in chunk:
                    self.execute(insert, row)
                chunk = []
        for row in chunk:
            self.execute(insert, row)
