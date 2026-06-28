"""Tests for Phase A: Slim CI, deferral, state engine hardening."""

import os
import shutil
import tempfile
import subprocess
from pathlib import Path

import pytest

from briq.core.ci import changed_models, changed_subgraph
from briq.state.engine import StateEngine
from briq.core.project import Project
from briq.core.executor import Executor
from briq.adapters.duckdb import DuckDBAdapter
from briq.core.config import WarehouseConfig


# ---------------------------------------------------------------------------
# State engine hardening
# ---------------------------------------------------------------------------

class TestStateEngineHardening:
    def test_wal_mode_enabled(self, tmp_path: Path):
        """WAL pragma set without error."""
        engine = StateEngine(tmp_path)
        # wal_autocheckpoint was set in init — verify no crash
        assert engine.conn is not None
        engine.close()

    def test_get_hash(self, tmp_path: Path):
        engine = StateEngine(tmp_path)
        assert engine.get_hash("nonexistent") is None
        engine.record_run("test_model", "abc123", 42)
        assert engine.get_hash("test_model") == "abc123"
        engine.close()

    def test_concurrent_safety(self, tmp_path: Path):
        engine = StateEngine(tmp_path)
        import threading
        errors = []
        def worker(i):
            try:
                engine.record_run(f"model_{i}", f"hash_{i}", i)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        states = engine.get_all_states()
        assert len(states) == 20
        engine.close()

    def test_reset_single(self, tmp_path: Path):
        engine = StateEngine(tmp_path)
        engine.record_run("a", "h1", 1)
        engine.record_run("b", "h2", 2)
        engine.reset("a")
        assert engine.get_hash("a") is None
        assert engine.get_hash("b") == "h2"
        engine.close()


# ---------------------------------------------------------------------------
# Slim CI — git-diff logic
# ---------------------------------------------------------------------------

class TestSlimCI:
    def test_changed_models_no_git(self, tmp_path: Path):
        """If not in a git repo, returns empty list without crashing."""
        result = changed_models(tmp_path)
        assert result == []

    def test_changed_subgraph_no_git(self, tmp_path: Path):
        """If not in a git repo, returns empty list."""
        result = changed_subgraph(tmp_path)
        assert result == []

    def test_changed_models_git_repo(self, tmp_path: Path):
        """In a git repo, detects .sql file changes."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)

        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "unchanged.sql").write_text("SELECT 1")
        (models_dir / "changed.sql").write_text("SELECT 2")

        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)

        (models_dir / "changed.sql").write_text("SELECT 3")  # modify
        (models_dir / "new.sql").write_text("SELECT 4")      # add

        models = changed_models(tmp_path)
        assert "changed" in models
        assert "new" in models
        assert "unchanged" not in models

    def test_changed_subgraph_returns_at_prefix(self, tmp_path: Path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)

        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "m.sql").write_text("SELECT 1")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        (models_dir / "m.sql").write_text("SELECT 2")
        sel = changed_subgraph(tmp_path)
        assert sel == ["@m"]


# ---------------------------------------------------------------------------
# Defer to prod
# ---------------------------------------------------------------------------

class TestDefer:
    def test_defer_skips_matching_hash(self, tmp_path: Path):
        """If defer state has matching hash, model is skipped."""
        # Create project with a model
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        models_dir = project_dir / "models"
        models_dir.mkdir()
        (project_dir / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "my_model.sql").write_text("SELECT 1 AS x")

        project = Project(project_dir)

        # Create a "production" state with the same hash
        prod_state = StateEngine(project_dir / "target_prod")
        executor = Executor(project, None, None)
        model_hash = executor.compute_model_hash("my_model")
        prod_state.record_run("my_model", model_hash, 100)
        prod_state.close()

        # Now run with defer pointing to prod
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        state = StateEngine(project_dir)
        executor = Executor(project, adapter, state)
        results = executor.run(defer=project_dir / "target_prod")

        assert len(results["skipped"]) == 1
        assert results["skipped"][0]["error"] == "Up to date (deferred)"
        adapter.disconnect()
        state.close()

    def test_defer_runs_if_hash_differs(self, tmp_path: Path):
        """If defer state has different hash, model is executed."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        models_dir = project_dir / "models"
        models_dir.mkdir()
        (project_dir / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "my_model.sql").write_text("SELECT 1 AS x")

        project = Project(project_dir)

        # Prod state with DIFFERENT hash
        prod_state = StateEngine(project_dir / "target_prod")
        prod_state.record_run("my_model", "oldhash", 100)
        prod_state.close()

        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        state = StateEngine(project_dir)
        executor = Executor(project, adapter, state)
        results = executor.run(defer=project_dir / "target_prod")

        assert len(results["success"]) == 1
        adapter.disconnect()
        state.close()

    def test_defer_nonexistent_fallback(self, tmp_path: Path):
        """If defer path doesn't exist, runs full build with warning."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        models_dir = project_dir / "models"
        models_dir.mkdir()
        (project_dir / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "my_model.sql").write_text("SELECT 1 AS x")

        project = Project(project_dir)
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        state = StateEngine(project_dir)
        executor = Executor(project, adapter, state)
        import warnings
        with warnings.catch_warnings(record=True) as w:
            results = executor.run(defer="nonexistent_path.duckdb")
            assert any("not found" in str(m.message).lower() for m in w)
        assert len(results["success"]) == 1
        adapter.disconnect()
        state.close()
