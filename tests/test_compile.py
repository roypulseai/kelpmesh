"""Tests for briq compile — applies substitutions without hitting warehouse."""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path
from typer.testing import CliRunner

from briq.cli.main import app

runner = CliRunner()


def _setup(tmp_path: Path, models: dict[str, str], cfg_override: dict | None = None):
    (tmp_path / "models").mkdir(exist_ok=True)
    for name, sql in models.items():
        (tmp_path / "models" / f"{name}.sql").write_text(sql, encoding="utf-8")
    cfg = {
        "warehouse": {"type": "duckdb", "path": ":memory:"},
        "models_path": "models",
        "target_path": "target",
        **(cfg_override or {}),
    }
    (tmp_path / "briq.yml").write_text(yaml.dump(cfg), encoding="utf-8")
    return tmp_path


class TestCompileCommand:
    def test_compiles_to_file(self, tmp_path):
        _setup(tmp_path, {"my_model": "SELECT 1 AS x"})
        result = runner.invoke(app, ["compile", "--project-dir", str(tmp_path)])
        assert result.exit_code == 0
        compiled = tmp_path / "target" / "compiled" / "my_model.sql"
        assert compiled.exists()
        assert "SELECT 1 AS x" in compiled.read_text()

    def test_var_substitution_in_compile(self, tmp_path):
        sql = "WHERE dt >= '{{ var(\"start\") }}'"
        _setup(tmp_path, {"model": sql})
        result = runner.invoke(
            app, ["compile", "--project-dir", str(tmp_path), "--var", "start=2025-01-01"]
        )
        assert result.exit_code == 0
        compiled = tmp_path / "target" / "compiled" / "model.sql"
        assert "2025-01-01" in compiled.read_text()

    def test_incremental_flag_keeps_block(self, tmp_path):
        sql = (
            "SELECT * FROM source\n"
            "{% if is_incremental() %}\nWHERE updated_at > '2025-01-01'\n{% endif %}"
        )
        _setup(tmp_path, {"inc": sql})
        result = runner.invoke(
            app, ["compile", "--project-dir", str(tmp_path), "--incremental"]
        )
        assert result.exit_code == 0
        compiled = tmp_path / "target" / "compiled" / "inc.sql"
        assert "WHERE updated_at" in compiled.read_text()

    def test_without_incremental_flag_removes_block(self, tmp_path):
        sql = (
            "SELECT * FROM source\n"
            "{% if is_incremental() %}\nWHERE updated_at > '2025-01-01'\n{% endif %}"
        )
        _setup(tmp_path, {"inc": sql})
        result = runner.invoke(app, ["compile", "--project-dir", str(tmp_path)])
        assert result.exit_code == 0
        compiled = tmp_path / "target" / "compiled" / "inc.sql"
        assert "WHERE updated_at" not in compiled.read_text()

    def test_print_to_stdout(self, tmp_path):
        _setup(tmp_path, {"model": "SELECT 42 AS answer"})
        result = runner.invoke(
            app, ["compile", "--project-dir", str(tmp_path), "--print"]
        )
        assert result.exit_code == 0
        assert "42" in result.output

    def test_select_single_model(self, tmp_path):
        _setup(tmp_path, {"a": "SELECT 1", "b": "SELECT 2"})
        result = runner.invoke(
            app, ["compile", "--project-dir", str(tmp_path), "--select", "a"]
        )
        assert result.exit_code == 0
        assert (tmp_path / "target" / "compiled" / "a.sql").exists()
        assert not (tmp_path / "target" / "compiled" / "b.sql").exists()

    def test_tag_selection(self, tmp_path):
        _setup(tmp_path, {
            "tagged": "-- tags: finance\nSELECT 1",
            "other": "SELECT 2",
        })
        result = runner.invoke(
            app, ["compile", "--project-dir", str(tmp_path), "--tag", "finance"]
        )
        assert result.exit_code == 0
        assert (tmp_path / "target" / "compiled" / "tagged.sql").exists()
        assert not (tmp_path / "target" / "compiled" / "other.sql").exists()

    def test_custom_output_dir(self, tmp_path):
        _setup(tmp_path, {"model": "SELECT 1"})
        out = tmp_path / "custom_out"
        result = runner.invoke(
            app, ["compile", "--project-dir", str(tmp_path), "--output", str(out)]
        )
        assert result.exit_code == 0
        assert (out / "model.sql").exists()

    def test_no_models_exits_cleanly(self, tmp_path):
        (tmp_path / "models").mkdir()
        cfg = {"warehouse": {"type": "duckdb", "path": ":memory:"}, "models_path": "models", "target_path": "target"}
        (tmp_path / "briq.yml").write_text(yaml.dump(cfg), encoding="utf-8")
        result = runner.invoke(app, ["compile", "--project-dir", str(tmp_path)])
        assert result.exit_code == 0
