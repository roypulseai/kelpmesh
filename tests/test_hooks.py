"""Tests for pre/post hook execution in the Executor."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call, patch
from pathlib import Path


def _make_project(tmp_path: Path, models: dict[str, str], config_override=None):
    """Build a minimal project with given SQL models."""
    (tmp_path / "models").mkdir(exist_ok=True)
    for name, sql in models.items():
        (tmp_path / "models" / f"{name}.sql").write_text(sql, encoding="utf-8")

    cfg = {
        "warehouse": {"type": "duckdb", "path": ":memory:"},
        "models_path": "models",
        "target_path": "target",
        **(config_override or {}),
    }
    import yaml
    (tmp_path / "briq.yml").write_text(yaml.dump(cfg), encoding="utf-8")


def _make_executor(tmp_path, models, adapter=None):
    from briq.core.project import Project
    from briq.core.executor import Executor
    from briq.state.engine import StateEngine

    _make_project(tmp_path, models)
    project = Project(tmp_path)
    if adapter is None:
        adapter = MagicMock()
        adapter.table_exists.return_value = False
        adapter.fetch_row_count.return_value = 0
        adapter.acquire_conn.return_value = None
        adapter.release_conn.return_value = None
    state = StateEngine(tmp_path)
    executor = Executor(project, adapter, state)
    executor.dag.build()
    return executor, adapter


class TestPrePostHooks:
    def test_pre_hook_parsed_from_comment(self, tmp_path):
        sql = (
            "-- pre_hook: GRANT SELECT ON {{ this }} TO reporter\n"
            "SELECT 1 AS x"
        )
        _make_project(tmp_path, {"my_model": sql})
        from briq.core.project import Project
        p = Project(tmp_path)
        model = p.get_model("my_model")
        assert model.pre_hook == ["GRANT SELECT ON {{ this }} TO reporter"]

    def test_post_hook_parsed_from_comment(self, tmp_path):
        sql = (
            "-- post_hook: ANALYZE {{ this }}\n"
            "SELECT 1 AS x"
        )
        _make_project(tmp_path, {"my_model": sql})
        from briq.core.project import Project
        p = Project(tmp_path)
        model = p.get_model("my_model")
        assert model.post_hook == ["ANALYZE {{ this }}"]

    def test_multiple_hooks(self, tmp_path):
        sql = (
            "-- pre_hook: GRANT SELECT ON {table} TO r1\n"
            "-- pre_hook: GRANT SELECT ON {table} TO r2\n"
            "SELECT 1 AS x"
        )
        _make_project(tmp_path, {"my_model": sql})
        from briq.core.project import Project
        p = Project(tmp_path)
        model = p.get_model("my_model")
        assert len(model.pre_hook) == 2

    def test_run_hooks_calls_adapter_execute(self, tmp_path):
        executor, adapter = _make_executor(tmp_path, {"m": "SELECT 1"})
        adapter.execute = MagicMock()
        executor._run_hooks(["GRANT SELECT ON my_table TO r"], "my_table")
        adapter.execute.assert_called_once_with("GRANT SELECT ON my_table TO r", conn=None)

    def test_run_hooks_table_placeholder_substitution(self, tmp_path):
        executor, adapter = _make_executor(tmp_path, {"m": "SELECT 1"})
        adapter.execute = MagicMock()
        executor._run_hooks(["ANALYZE {table}"], "orders_daily")
        called_sql = adapter.execute.call_args[0][0]
        assert "orders_daily" in called_sql
        assert "{table}" not in called_sql

    def test_enabled_false_skips_model(self, tmp_path):
        sql = "-- enabled: false\nSELECT 1"
        executor, adapter = _make_executor(tmp_path, {"disabled_model": sql})
        adapter.execute_model = MagicMock()
        results = executor.run()
        assert not any(r["name"] == "disabled_model" and r["error"] is None
                       for r in results["success"])
        adapter.execute_model.assert_not_called()
