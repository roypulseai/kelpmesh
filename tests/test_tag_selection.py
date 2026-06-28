"""Tests for tag-based model selection in DAGBuilder.select_models."""

from __future__ import annotations

import pytest
from pathlib import Path
import yaml


def _setup_project(tmp_path: Path, models: dict[str, str]) -> "Project":
    (tmp_path / "models").mkdir(exist_ok=True)
    for name, sql in models.items():
        (tmp_path / "models" / f"{name}.sql").write_text(sql, encoding="utf-8")
    cfg = {"warehouse": {"type": "duckdb", "path": ":memory:"}, "models_path": "models", "target_path": "target"}
    (tmp_path / "kelpmesh.yml").write_text(yaml.dump(cfg), encoding="utf-8")
    from kelpmesh.core.project import Project
    return Project(tmp_path)


class TestTagSelection:
    def test_single_tag_match(self, tmp_path):
        models = {
            "finance_orders": "-- tags: finance\nSELECT 1",
            "marketing_clicks": "-- tags: marketing\nSELECT 2",
        }
        project = _setup_project(tmp_path, models)
        from kelpmesh.core.graph import DAGBuilder
        dag = DAGBuilder(project)
        dag.build()
        selected = dag.select_models(tags=["finance"])
        assert "finance_orders" in selected
        assert "marketing_clicks" not in selected

    def test_multiple_tags_union(self, tmp_path):
        models = {
            "finance_orders": "-- tags: finance\nSELECT 1",
            "marketing_clicks": "-- tags: marketing\nSELECT 2",
            "core_users": "SELECT 3",
        }
        project = _setup_project(tmp_path, models)
        from kelpmesh.core.graph import DAGBuilder
        dag = DAGBuilder(project)
        dag.build()
        selected = dag.select_models(tags=["finance", "marketing"])
        assert "finance_orders" in selected
        assert "marketing_clicks" in selected
        assert "core_users" not in selected

    def test_tag_prefix_in_select_string(self, tmp_path):
        models = {
            "finance_orders": "-- tags: finance\nSELECT 1",
            "other": "SELECT 2",
        }
        project = _setup_project(tmp_path, models)
        from kelpmesh.core.graph import DAGBuilder
        dag = DAGBuilder(project)
        dag.build()
        selected = dag.select_models(select=["tag:finance"])
        assert "finance_orders" in selected
        assert "other" not in selected

    def test_no_filters_execution_order_has_all(self, tmp_path):
        models = {
            "a": "SELECT 1",
            "b": "SELECT 2",
        }
        project = _setup_project(tmp_path, models)
        from kelpmesh.core.graph import DAGBuilder
        dag = DAGBuilder(project)
        dag.build()
        # execution_order() with no args returns all models in topo order
        all_models = dag.execution_order()
        assert set(all_models) == {"a", "b"}

    def test_no_matching_tag_returns_empty(self, tmp_path):
        models = {
            "finance_orders": "-- tags: finance\nSELECT 1",
        }
        project = _setup_project(tmp_path, models)
        from kelpmesh.core.graph import DAGBuilder
        dag = DAGBuilder(project)
        dag.build()
        selected = dag.select_models(tags=["nonexistent"])
        assert selected == [] or set(selected) == set()

    def test_multiple_tags_on_one_model(self, tmp_path):
        models = {
            "hybrid": "-- tags: finance,reporting\nSELECT 1",
        }
        project = _setup_project(tmp_path, models)
        from kelpmesh.core.graph import DAGBuilder
        dag = DAGBuilder(project)
        dag.build()
        selected = dag.select_models(tags=["reporting"])
        assert "hybrid" in selected

    def test_combined_select_and_tag(self, tmp_path):
        models = {
            "base": "SELECT 1",
            "orders": "-- tags: finance\n-- depends_on: ref('base')\nSELECT * FROM base",
            "other": "SELECT 3",
        }
        project = _setup_project(tmp_path, models)
        from kelpmesh.core.graph import DAGBuilder
        dag = DAGBuilder(project)
        dag.build()
        # Select by tag; base is a dep of orders but untagged
        selected = dag.select_models(tags=["finance"])
        assert "orders" in selected
