import hashlib
import re
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from pathlib import Path
from typing import Callable
from briq.core.project import Project
from briq.core.graph import DAGBuilder
from briq.core.errors import sanitize_exception
from briq.core.ci import changed_subgraph
from briq.adapters.base import WarehouseAdapter, sanitize_name
from briq.state.engine import StateEngine

_EXTERNAL_URL_RE = re.compile(
    r"(https?://|s3://|gs://|az://|gcs://|wasbs?://|abfss?://|adl://)"
)
_EXTERNAL_DB_RE = re.compile(
    r"(?i)\b(read_csv|read_parquet|read_json|read_excel|"
    r"postgresql|mysql|sqlite|mssql|snowflake|bigquery|redshift)\s*\("
)

_SECURITY_AUDITS: dict[str, object] = {}


def _get_audit(project):
    from briq.security.audit import AuditLog
    key = str(project.path.resolve())
    if key not in _SECURITY_AUDITS:
        _SECURITY_AUDITS[key] = AuditLog(project.path)
    return _SECURITY_AUDITS[key]


class Executor:
    def __init__(
        self,
        project: Project,
        adapter: WarehouseAdapter,
        state: StateEngine | None = None,
        threads: int = 4,
    ):
        self.project = project
        self.adapter = adapter
        self.state = state or StateEngine(project.path)
        self.threads = threads
        self.dag = DAGBuilder(project)

    def resolve_ephemeral(self, model_name: str) -> str:
        model = self.project.get_model(model_name)
        if not model:
            return ""
        if model.language == "python":
            return ""
        sql = model.sql or ""
        for up_name in sorted(model.upstream):
            up_model = self.project.get_model(up_name)
            if up_model and up_model.materialized == "ephemeral":
                cte_name = up_name
                cte_sql = up_model.sql or ""
                sql = f"WITH {cte_name} AS ({cte_sql})\n{sql}"
        return sql

    def compute_model_hash(self, model_name: str) -> str:
        model = self.project.get_model(model_name)
        if not model:
            return ""
        content = model.python_code if model.language == "python" else (model.sql or "")
        for up in sorted(model.upstream):
            up_hash = self.compute_model_hash(up)
            content += up_hash
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _check_external_access(self, sql: str, model_name: str):
        """Warn if SQL reads external URLs or connects to external databases."""
        if _EXTERNAL_URL_RE.search(sql):
            warnings.warn(
                f"[data-leak] {model_name}: references external URL. "
                f"Ensure no sensitive data is exfiltrated.",
                stacklevel=2,
            )
        if _EXTERNAL_DB_RE.search(sql):
            warnings.warn(
                f"[data-leak] {model_name}: reads from external data source. "
                f"Verify data flow complies with policy.",
                stacklevel=2,
            )

    def _make_python_ref(self, python_conn):
        """Build a ref() function for Python model execution namespace."""
        def ref(name: str):
            model = self.project.get_model(name)
            if not model:
                raise NameError(f"Unknown model referenced in Python: {name}")
            table_name = model.relation_name
            return python_conn.sql(f"SELECT * FROM {sanitize_name(table_name)}")
        return ref

    def _ensure_python_conn(self, preferred_conn=None):
        """Get a DuckDB connection for Python model execution.

        Uses *adapter.conn* when available to avoid cross-connection
        isolation with ``:memory:`` databases. Falls back to
        *preferred_conn*, then creates a new ``:memory:`` connection.
        """
        if hasattr(self.adapter, "conn"):
            if self.adapter.conn is not None:
                return self.adapter.conn
            if hasattr(self.adapter, "connect"):
                self.adapter.connect()
                if self.adapter.conn is not None:
                    return self.adapter.conn
        if preferred_conn is not None:
            return preferred_conn
        import duckdb
        return duckdb.connect(":memory:")

    def _execute_python_model(self, model, python_conn=None):
        """Execute a Python model and return the result relation."""
        if python_conn is None:
            python_conn = self._ensure_python_conn()
        import inspect
        ns = {
            "ref": self._make_python_ref(python_conn),
        }
        exec(model.python_code, ns)
        if "model" not in ns:
            raise RuntimeError(f"Python model '{model.name}' must define a 'model' function")
        fn = ns["model"]
        sig = inspect.signature(fn)
        kwargs = {}
        for param in sig.parameters:
            if param in ns:
                kwargs[param] = ns[param]
        result = fn(**kwargs)
        return result

    def _materialize_python_result(self, model, result, python_conn=None):
        """Write a Python model result (DataFrame/relation) to the warehouse."""
        import duckdb
        if python_conn is None:
            python_conn = self._ensure_python_conn()
        table_name = model.relation_name
        if isinstance(result, duckdb.DuckDBPyRelation):
            python_conn.execute(f"CREATE OR REPLACE TABLE {sanitize_name(table_name)} AS SELECT * FROM result")
        else:
            import pandas as pd
            if isinstance(result, pd.DataFrame):
                python_conn.register("_py_df", result)
            elif hasattr(result, "toPandas"):
                import warnings as _w
                _w.warn(f"Python model '{model.name}': converting to pandas", stacklevel=2)
                python_conn.register("_py_df", result.toPandas())
            elif hasattr(result, "fetchdf"):
                python_conn.register("_py_df", result.fetchdf())
            else:
                python_conn.register("_py_df", pd.DataFrame(result))
            python_conn.execute(f"CREATE OR REPLACE TABLE {sanitize_name(table_name)} AS SELECT * FROM _py_df")

    def run(
        self,
        model_names: list[str] | None = None,
        select: list[str] | None = None,
        role: str | None = None,
        changed: bool = False,
        changed_against: str | None = None,
        defer: Path | str | None = None,
        progress_cb: Callable[[str, str, float], None] | None = None,
    ) -> dict:
        if changed:
            select = (select or []) + changed_subgraph(self.project.path, changed_against)
        if select:
            model_names = self.dag.select_models(select)
        order = self.dag.execution_order(model_names)

        # Load defer state if requested
        self._defer_state = None
        if defer:
            defer_path = Path(defer)
            if not defer_path.suffix:
                # Treated as project directory — look for target/briq_state.duckdb
                defer_path = defer_path / "target" / "briq_state.duckdb"
            if defer_path.exists():
                self._defer_state = StateEngine.open_readonly(defer_path)
                warnings.warn(f"Deferring to state at {defer_path}", stacklevel=2)
            else:
                warnings.warn(f"Defer target not found: {defer}. Running full build.", stacklevel=2)
        results = {"success": [], "skipped": [], "failed": []}
        audit = _get_audit(self.project)
        audit.record(
            action="run",
            actor=role or "cli",
            resource=f"models:{','.join(order[:5])}" + (f"...+{len(order)-5}" if len(order) > 5 else ""),
            detail=f"Executing {len(order)} models with role={role}",
        )

        if self.threads <= 1:
            return self._run_sequential(order, results, progress_cb=progress_cb)

        return self._run_parallel(order, results, progress_cb=progress_cb)

    def _run_sequential(
        self,
        order: list[str],
        results: dict,
        progress_cb: Callable[[str, str, float], None] | None = None,
    ) -> dict:
        for name in order:
            model = self.project.get_model(name)
            if not model:
                results["failed"].append({"name": name, "error": "Model not found", "elapsed": 0.0})
                if progress_cb:
                    progress_cb(name, "failed", 0.0)
                continue

            model_hash = self.compute_model_hash(name)

            # Defer: skip if hash matches production state
            if self._defer_state is not None:
                prod_hash = self._defer_state.get_hash(name)
                if prod_hash == model_hash:
                    results["skipped"].append({"name": name, "error": "Up to date (deferred)", "elapsed": 0.0})
                    if progress_cb:
                        progress_cb(name, "skipped", 0.0)
                    continue

            if self.state and self.state.is_up_to_date(name, model_hash):
                results["skipped"].append({"name": name, "error": "Up to date", "elapsed": 0.0})
                if progress_cb:
                    progress_cb(name, "skipped", 0.0)
                continue

            if model.materialized == "ephemeral":
                results["success"].append({"name": name, "error": None, "elapsed": 0.0})
                if progress_cb:
                    progress_cb(name, "success", 0.0)
                continue

            t0 = time.monotonic()
            try:
                table_name = model.alias or name
                if model.language == "python":
                    result = self._execute_python_model(model)
                    self._materialize_python_result(model, result)
                else:
                    sql = self.resolve_ephemeral(name)
                    self._check_external_access(sql, name)
                    self.adapter.execute_model(
                        sql=sql,
                        table_name=table_name,
                        materialized=model.materialized,
                        unique_key=model.unique_key,
                        incremental_strategy=model.incremental_strategy,
                    )
                elapsed = time.monotonic() - t0
                if self.state:
                    row_count = self.adapter.fetch_row_count(table_name)
                    self.state.record_run(name, model_hash, row_count)
                results["success"].append({"name": name, "error": None, "elapsed": elapsed})
                if progress_cb:
                    progress_cb(name, "success", elapsed)
                _get_audit(self.project).record(
                    action="model.run",
                    actor="cli",
                    resource=f"model:{name}",
                    status="success",
                    detail=f"Rows: {row_count if self.state else 'N/A'}",
                )
            except Exception as e:
                elapsed = time.monotonic() - t0
                safe = sanitize_exception(e)
                results["failed"].append({"name": name, "error": safe, "elapsed": elapsed})
                if progress_cb:
                    progress_cb(name, "failed", elapsed)
                _get_audit(self.project).record(
                    action="model.run",
                    actor="cli",
                    resource=f"model:{name}",
                    status="failed",
                    detail=safe[:200],
                )

        return results

    def _run_parallel(
        self,
        order: list[str],
        results: dict,
        progress_cb: Callable[[str, str, float], None] | None = None,
    ) -> dict:
        if hasattr(self.adapter, "init_pool"):
            self.adapter.init_pool(self.threads)

        completed = set()
        pending = set(order)

        def is_ready(name: str) -> bool:
            model = self.project.models.get(name)
            if not model:
                return True
            for dep in model.upstream:
                if dep in order and dep not in completed:
                    return False
            return True

        def execute_model(name: str):
            model = self.project.get_model(name)
            if not model:
                return name, "failed", "Model not found", 0.0

            model_hash = self.compute_model_hash(name)

            if self._defer_state is not None:
                prod_hash = self._defer_state.get_hash(name)
                if prod_hash == model_hash:
                    return name, "skipped", "Up to date (deferred)", 0.0

            if self.state and self.state.is_up_to_date(name, model_hash):
                return name, "skipped", "Up to date", 0.0

            if model.materialized == "ephemeral":
                return name, "success", None, 0.0

            conn = None
            t0 = time.monotonic()
            try:
                conn = self.adapter.acquire_conn()
                table_name = model.alias or name
                if model.language == "python":
                    result = self._execute_python_model(model, python_conn=conn)
                    self._materialize_python_result(model, result, python_conn=conn)
                else:
                    sql = self.resolve_ephemeral(name)
                    self._check_external_access(sql, name)
                    self.adapter.execute_model(
                        sql=sql,
                        table_name=table_name,
                        materialized=model.materialized,
                        conn=conn,
                        unique_key=model.unique_key,
                        incremental_strategy=model.incremental_strategy,
                    )
                elapsed = time.monotonic() - t0
                if self.state:
                    row_count = self.adapter.fetch_row_count(table_name, conn=conn)
                    self.state.record_run(name, model_hash, row_count)
                _get_audit(self.project).record(
                    action="model.run",
                    actor="cli",
                    resource=f"model:{name}",
                    status="success",
                    detail=f"Rows: {row_count if self.state else 'N/A'}",
                )
                return name, "success", None, elapsed
            except Exception as e:
                elapsed = time.monotonic() - t0
                safe = sanitize_exception(e)
                _get_audit(self.project).record(
                    action="model.run",
                    actor="cli",
                    resource=f"model:{name}",
                    status="failed",
                    detail=safe[:200],
                )
                return name, "failed", safe, elapsed
            finally:
                if conn is not None:
                    self.adapter.release_conn(conn)

        with ThreadPoolExecutor(max_workers=self.threads) as pool:
            fut_map = {}

            while pending or fut_map:
                ready = [n for n in pending if is_ready(n)]
                if not ready and not fut_map:
                    break

                for name in ready:
                    pending.discard(name)
                    fut = pool.submit(execute_model, name)
                    fut_map[fut] = name

                if not fut_map:
                    break

                done, _ = wait(fut_map, return_when=FIRST_COMPLETED, timeout=1.0)

                if not done:
                    continue

                for fut in done:
                    name, status, msg, elapsed = fut.result()
                    results[status].append({"name": name, "error": msg, "elapsed": elapsed})
                    completed.add(name)
                    del fut_map[fut]
                    if progress_cb:
                        progress_cb(name, status, elapsed)

        return results
