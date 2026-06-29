"""Python model execution — run models/*.py files against the warehouse.

Interface for model authors:

    # models/my_active_users.py
    def model(dbt, session):
        users = dbt.ref('stg_users')
        events = dbt.ref('stg_events')
        return f'''
            SELECT u.user_id, u.email, MAX(e.event_time) AS last_seen
            FROM {users} u
            JOIN {events} e USING (user_id)
            WHERE u.is_active
            GROUP BY 1, 2
        '''

    # Optionally return a pandas DataFrame instead of SQL:
    def model(dbt, session):
        import pandas as pd
        upstream = dbt.ref('raw_scores')
        rows = session.execute(f"SELECT * FROM {upstream}")
        df = pd.DataFrame(rows)
        df['score_normalized'] = df['score'] / df['score'].max()
        return df

The model() function receives:
  - dbt    : DbtProxy   — provides ref(), source(), config(), var()
  - session: SessionProxy — provides execute(sql) → list[dict]

Return value:
  - str (SQL)         → executed as CREATE TABLE AS / INSERT / MERGE
  - pandas.DataFrame  → written to the warehouse via adapter._write_df()
"""

from __future__ import annotations

__all__ = ["PythonModelRunner", "DbtProxy", "SessionProxy"]

import importlib.util
import inspect
from pathlib import Path
from typing import Any


class DbtProxy:
    """Minimal dbt-compatible context passed to Python model functions."""

    def __init__(
        self,
        resolved_refs: dict[str, str],
        resolved_sources: dict[tuple[str, str], str],
        vars: dict[str, Any] | None = None,
        config: dict | None = None,
    ) -> None:
        self._refs = resolved_refs
        self._sources = resolved_sources
        self._vars = vars or {}
        self._config = config or {}

    def ref(self, model_name: str) -> str:
        """Return the fully qualified table name for *model_name*."""
        key = model_name.strip('"').strip('`')
        if key in self._refs:
            return self._refs[key]
        return f'"{key}"'

    def source(self, source_name: str, table_name: str) -> str:
        """Return the fully qualified table name for a source."""
        key = (source_name, table_name)
        if key in self._sources:
            return self._sources[key]
        return f'"{source_name}"."{table_name}"'

    def var(self, name: str, default: Any = None) -> Any:
        """Look up a project variable."""
        return self._vars.get(name, default)

    def config(self, **kwargs) -> None:
        """Accept config() calls from model — no-op at runtime (config is read
        from YAML; calling config() inside the Python function is supported for
        IDE compatibility but has no effect on execution)."""
        pass


class SessionProxy:
    """Thin wrapper around the warehouse adapter for use inside Python models."""

    def __init__(self, adapter) -> None:
        self._adapter = adapter

    def execute(self, sql: str) -> list[dict]:
        """Run *sql* and return rows as a list of dicts."""
        return self._adapter.execute(sql)

    def execute_df(self, sql: str):
        """Run *sql* and return a pandas DataFrame."""
        import pandas as pd
        rows = self._adapter.execute(sql)
        return pd.DataFrame(rows)


class PythonModelRunner:
    """Loads and executes a Python model file."""

    def __init__(self, adapter=None, resolved_refs: dict[str, str] | None = None,
                 resolved_sources: dict[tuple[str, str], str] | None = None,
                 vars: dict[str, Any] | None = None) -> None:
        if adapter is None:
            from kelpmesh.adapters.duckdb import DuckDBAdapter
            from kelpmesh.core.config import WarehouseConfig
            adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        self._adapter = adapter
        self._refs = resolved_refs or {}
        self._sources = resolved_sources or {}
        self._vars = vars or {}

    def run(self, model_path: Path, table_name: str,
            materialized: str = "table",
            unique_key: str | None = None,
            incremental_strategy: str = "merge",
            full_refresh: bool = False) -> None:
        """Execute a Python model and materialize the result."""
        fn = self._load_model_fn(model_path)

        dbt = DbtProxy(self._refs, self._sources, self._vars)
        session = SessionProxy(self._adapter)

        result = fn(dbt, session)

        if result is None:
            return

        # DataFrame path
        try:
            import pandas as pd
            if isinstance(result, pd.DataFrame):
                self._adapter._write_df(result, table_name)
                return
        except ImportError:
            pass

        # SQL string path
        if isinstance(result, str):
            sql = result.strip()
            if not sql:
                return
            if materialized == "incremental" and not full_refresh:
                self._adapter.execute_model(
                    sql, table_name,
                    materialized="incremental",
                    unique_key=unique_key,
                    incremental_strategy=incremental_strategy,
                )
            else:
                self._adapter.execute_model(sql, table_name, materialized=materialized)
        else:
            raise TypeError(
                f"Python model {model_path.name} must return a SQL string or "
                f"pandas DataFrame, got {type(result).__name__}"
            )

    @staticmethod
    def _load_model_fn(model_path: Path) -> Any:
        """Import *model_path* and return its model() function."""
        spec = importlib.util.spec_from_file_location(
            f"_kelpmesh_py_model_{model_path.stem}", model_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load Python model: {model_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "model"):
            raise AttributeError(
                f"Python model {model_path.name} must define a "
                f"model(dbt, session) function."
            )
        fn = mod.model
        sig = inspect.signature(fn)
        if len(sig.parameters) < 2:
            raise TypeError(
                f"model() in {model_path.name} must accept (dbt, session) — "
                f"got {len(sig.parameters)} parameter(s)."
            )
        return fn

    @staticmethod
    def extract_refs(model_path: Path) -> list[str]:
        """Static analysis: extract ref() calls for DAG construction."""
        from kelpmesh.parser.python import PythonRefParser
        return PythonRefParser.extract_refs(model_path.read_text(encoding="utf-8"))

    @staticmethod
    def extract_sources(model_path: Path) -> list[str]:
        """Static analysis: extract source() calls for DAG construction."""
        from kelpmesh.parser.python import PythonRefParser
        return PythonRefParser.extract_sources(model_path.read_text(encoding="utf-8"))
