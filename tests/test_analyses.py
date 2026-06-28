"""Tests for analyses directory — models compiled but never materialized."""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path
from unittest.mock import MagicMock


def _setup_project(tmp_path: Path, models=None, analyses=None):
    (tmp_path / "models").mkdir(exist_ok=True)
    (tmp_path / "analyses").mkdir(exist_ok=True)

    for name, sql in (models or {}).items():
        (tmp_path / "models" / f"{name}.sql").write_text(sql, encoding="utf-8")

    for name, sql in (analyses or {}).items():
        (tmp_path / "analyses" / f"{name}.sql").write_text(sql, encoding="utf-8")

    cfg = {
        "warehouse": {"type": "duckdb", "path": ":memory:"},
        "models_path": "models",
        "analyses_path": "analyses",
        "target_path": "target",
    }
    (tmp_path / "kelpmesh.yml").write_text(yaml.dump(cfg), encoding="utf-8")
    from kelpmesh.core.project import Project
    return Project(tmp_path)


class TestAnalysesLoading:
    def test_analysis_loaded_with_correct_materialization(self, tmp_path):
        project = _setup_project(
            tmp_path,
            analyses={"revenue_by_region": "SELECT region, SUM(revenue) FROM orders GROUP BY 1"},
        )
        model = project.get_model("revenue_by_region")
        assert model is not None
        assert model.materialized == "analysis"

    def test_analysis_and_model_coexist(self, tmp_path):
        project = _setup_project(
            tmp_path,
            models={"orders": "SELECT 1 AS id"},
            analyses={"ad_hoc": "SELECT COUNT(*) FROM orders"},
        )
        assert project.get_model("orders") is not None
        assert project.get_model("orders").materialized != "analysis"
        assert project.get_model("ad_hoc").materialized == "analysis"

    def test_analysis_not_materialized_in_run(self, tmp_path):
        project = _setup_project(
            tmp_path,
            analyses={"my_analysis": "SELECT 1"},
        )
        from kelpmesh.core.executor import Executor
        from kelpmesh.state.engine import StateEngine

        adapter = MagicMock()
        adapter.table_exists.return_value = False
        adapter.fetch_row_count.return_value = 0
        state = StateEngine(tmp_path)
        executor = Executor(project, adapter, state)
        executor.dag.build()
        results = executor.run()
        adapter.execute_model.assert_not_called()
        # The analysis is recorded as success (no-op)
        names = [r["name"] for r in results["success"]]
        assert "my_analysis" in names

    def test_empty_analyses_dir_no_error(self, tmp_path):
        project = _setup_project(
            tmp_path,
            models={"orders": "SELECT 1"},
        )
        # No analyses in the dir — project should load fine
        assert project.get_model("orders") is not None

    def test_analysis_dir_missing_no_error(self, tmp_path):
        (tmp_path / "models").mkdir(exist_ok=True)
        (tmp_path / "models" / "orders.sql").write_text("SELECT 1", encoding="utf-8")
        cfg = {"warehouse": {"type": "duckdb", "path": ":memory:"}, "models_path": "models", "target_path": "target"}
        (tmp_path / "kelpmesh.yml").write_text(yaml.dump(cfg), encoding="utf-8")
        from kelpmesh.core.project import Project
        # analyses_path doesn't exist — should not raise
        project = Project(tmp_path)
        assert project.get_model("orders") is not None
