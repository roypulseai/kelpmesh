"""Performance benchmark: measure parse, DAG build, and state check times for 100+ models."""
import time
from pathlib import Path
import tempfile


def _generate_large_project(tmpdir: Path, count: int):
    models = tmpdir / "models"
    models.mkdir(parents=True, exist_ok=True)
    (tmpdir / "kelpmesh.yml").write_text(
        "name: perf_test\n"
        "models_path: models\n"
        "target_path: target\n"
        "warehouse:\n"
        "  type: duckdb\n"
        "  path: target/perf.duckdb\n",
        encoding="utf-8",
    )
    (models / "model_000.sql").write_text(
        "SELECT 1 AS id", encoding="utf-8"
    )
    for i in range(1, count):
        prev = f"model_{i-1:03d}"
        curr = f"model_{i:03d}"
        sql = f"SELECT id, COUNT(*) AS cnt FROM {prev} GROUP BY 1"
        (models / f"{curr}.sql").write_text(sql, encoding="utf-8")


class TestPerformance:
    """Benchmark performance metrics for large projects."""

    def test_parse_100_models(self):
        tmpdir = Path(tempfile.mkdtemp())
        _generate_large_project(tmpdir, 100)

        from kelpmesh.core.project import Project
        start = time.perf_counter()
        project = Project(tmpdir)
        elapsed = time.perf_counter() - start
        assert len(project.models) == 100
        print(f"\n[perf] Load 100 models: {elapsed:.3f}s")
        assert elapsed < 5.0, f"Loading 100 models took {elapsed:.3f}s (limit 5s)"

    def test_dag_build_100_models(self):
        tmpdir = Path(tempfile.mkdtemp())
        _generate_large_project(tmpdir, 100)

        from kelpmesh.core.project import Project
        from kelpmesh.core.graph import DAGBuilder
        project = Project(tmpdir)
        dag = DAGBuilder(project)
        start = time.perf_counter()
        order = dag.execution_order()
        elapsed = time.perf_counter() - start
        assert len(order) == 100
        print(f"\n[perf] DAG build + topo sort 100 models: {elapsed:.3f}s")
        assert elapsed < 2.0, f"DAG build took {elapsed:.3f}s (limit 2s)"

    def test_state_check_100_models(self):
        tmpdir = Path(tempfile.mkdtemp())
        _generate_large_project(tmpdir, 100)

        from kelpmesh.core.project import Project
        from kelpmesh.core.executor import Executor
        from kelpmesh.state.engine import StateEngine
        from kelpmesh.adapters import get_adapter
        project = Project(tmpdir)
        adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
        state = StateEngine(project.path)
        executor = Executor(project, adapter, state)

        start = time.perf_counter()
        for name in project.models:
            h = executor.compute_model_hash(name)
            state.is_up_to_date(name, h)
        elapsed = time.perf_counter() - start
        print(f"\n[perf] State check 100 models: {elapsed:.3f}s")
        assert elapsed < 3.0, f"State check took {elapsed:.3f}s (limit 3s)"
        adapter.disconnect()
        state.close()
