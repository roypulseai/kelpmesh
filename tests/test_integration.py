from pathlib import Path
from typer.testing import CliRunner
from briq.cli.main import app
import tempfile
import json


runner = CliRunner()


def _project_files(tmpdir: Path):
    (tmpdir / "briq.yml").write_text(
        "name: test_project\n"
        "models_path: models\n"
        "tests_path: tests\n"
        "target_path: target\n"
        "warehouse:\n"
        "  type: duckdb\n"
        "  path: target/test.duckdb\n",
        encoding="utf-8",
    )
    models = tmpdir / "models"
    models.mkdir(parents=True, exist_ok=True)
    tests = tmpdir / "tests"
    tests.mkdir(parents=True, exist_ok=True)

    (models / "raw.sql").write_text("SELECT 1 AS id, 'alice' AS name", encoding="utf-8")
    (models / "cleaned.sql").write_text(
        "SELECT id, name FROM raw WHERE id IS NOT NULL", encoding="utf-8"
    )
    (models / "aggregated.sql").write_text(
        "SELECT name, COUNT(*) AS cnt FROM cleaned GROUP BY 1", encoding="utf-8"
    )
    (tests / "raw_not_null.sql").write_text(
        "SELECT COUNT(*) AS failures FROM raw WHERE id IS NULL",
        encoding="utf-8",
    )
    (tests / "aggregated_positive.sql").write_text(
        "SELECT COUNT(*) AS failures FROM aggregated WHERE cnt <= 0",
        encoding="utf-8",
    )


class TestIntegration:
    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def _invoke(self, *args):
        return runner.invoke(app, [str(a) for a in args], catch_exceptions=False)

    def test_full_lifecycle(self):
        _project_files(self.tmpdir)
        p = str(self.tmpdir)

        r = self._invoke("run", "-p", p)
        assert r.exit_code == 0, f"run failed: {r.output}"
        assert "OK" in r.output
        assert "raw" in r.output
        assert "cleaned" in r.output
        assert "aggregated" in r.output

        r = self._invoke("ls", "-p", p)
        assert r.exit_code == 0
        assert "Up-to-date" in r.output
        assert "raw" in r.output

        r = self._invoke("test", "-p", p)
        assert r.exit_code == 0
        assert "PASS" in r.output

        r = self._invoke("run", "-p", p)
        assert r.exit_code == 0
        assert "SKIP" in r.output

        r = self._invoke("build", "-p", p)
        assert r.exit_code == 0
        assert "SKIP" in r.output
        assert "PASS" in r.output

        r = self._invoke("diff", "aggregated", "-p", p)
        assert r.exit_code == 0
        assert "aggregated" in r.output

        r = self._invoke("preview", "aggregated", "-p", p)
        assert r.exit_code == 0
        assert "cnt" in r.output

        r = self._invoke("schema", "diff", "-p", p)
        assert r.exit_code == 0
        assert "No schema drift" in r.output or "schema" in r.output

        r = self._invoke("docs", "-p", p)
        assert r.exit_code == 0
        assert (self.tmpdir / "target" / "docs" / "index.html").exists()

        r = self._invoke("debug", "-p", p)
        assert r.exit_code == 0
        assert "Models:" in r.output
        assert "Warehouse connection: OK" in r.output

        r = self._invoke("clean", "-p", p)
        assert r.exit_code == 0
        assert not (self.tmpdir / "target").exists()

    def test_run_with_select(self):
        _project_files(self.tmpdir)
        p = str(self.tmpdir)

        self._invoke("run", "-p", p)
        r = self._invoke("run", "--select", "+aggregated", "-p", p)
        assert r.exit_code == 0
        assert "aggregated" in r.output
        assert "cleaned" in r.output

    def test_run_fails_on_no_models(self):
        empty_dir = Path(tempfile.mkdtemp())
        (empty_dir / "models").mkdir()
        r = self._invoke("run", "-p", str(empty_dir))
        assert r.exit_code != 0
        assert "No models found" in r.output

    def test_seed_execute(self):
        p = str(self.tmpdir)
        seed_file = self.tmpdir / "seed_data.sql"
        seed_file.write_text("CREATE TABLE IF NOT EXISTS test_seed AS SELECT 1 AS x", encoding="utf-8")
        r = self._invoke("seed", str(seed_file), "-p", p)
        assert r.exit_code == 0
        assert "Seed data loaded" in r.output

    def test_init_scaffolds_project(self):
        target = Path(tempfile.mkdtemp())
        r = self._invoke("init", "-p", str(target))
        assert r.exit_code == 0, f"init failed: {r.output}"
        assert (target / "models").exists(), f"models dir not in {list(target.iterdir())}"
        assert (target / "tests").exists()
        assert (target / "briq.yml").exists()
