from pathlib import Path
from kelpmesh.core.project import Project
import tempfile


class TestProject:
    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        models_dir = self.tmpdir / "models"
        models_dir.mkdir()

        (models_dir / "source.sql").write_text(
            "SELECT 1 AS id, 'test' AS name", encoding="utf-8"
        )
        (models_dir / "dependent.sql").write_text(
            "SELECT id, name FROM source", encoding="utf-8"
        )

    def test_loads_models(self):
        project = Project(self.tmpdir)
        assert len(project.models) == 2

    def test_dependency_resolution(self):
        project = Project(self.tmpdir)
        source = project.get_model("source")
        dependent = project.get_model("dependent")
        assert source is not None
        assert dependent is not None
        assert "source" in dependent.upstream

    def test_upstream_functions(self):
        project = Project(self.tmpdir)
        upstream = project.get_upstream("dependent")
        assert "source" in upstream

    def test_file_path(self):
        project = Project(self.tmpdir)
        model = project.get_model("source")
        assert model.file_path.exists()
        assert model.file_path.suffix == ".sql"

    def test_config_no_file(self):
        project = Project(self.tmpdir)
        assert project.config.name == "briq_project"
