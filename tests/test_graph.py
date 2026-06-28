from pathlib import Path
from kelpmesh.core.project import Project
from kelpmesh.core.graph import DAGBuilder
import tempfile


class TestDAGBuilder:
    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        models_dir = self.tmpdir / "models"
        models_dir.mkdir()

        (models_dir / "raw.sql").write_text(
            "SELECT 1 AS id", encoding="utf-8"
        )
        (models_dir / "cleaned.sql").write_text(
            "SELECT * FROM raw WHERE id IS NOT NULL", encoding="utf-8"
        )
        (models_dir / "aggregated.sql").write_text(
            "SELECT id, COUNT(*) AS cnt FROM cleaned GROUP BY 1",
            encoding="utf-8",
        )

    def test_execution_order(self):
        project = Project(self.tmpdir)
        dag = DAGBuilder(project)
        order = dag.execution_order()
        assert order.index("raw") < order.index("cleaned")
        assert order.index("cleaned") < order.index("aggregated")

    def test_layers(self):
        project = Project(self.tmpdir)
        dag = DAGBuilder(project)
        layers = dag.layers()
        assert "raw" in layers[0]
        assert "cleaned" in layers[1]
        assert "aggregated" in layers[2]

    def test_upstream_models(self):
        project = Project(self.tmpdir)
        dag = DAGBuilder(project)
        dag.build()
        upstream = dag.upstream_models("aggregated")
        assert "raw" in upstream
        assert "cleaned" in upstream

    def test_downstream_models(self):
        project = Project(self.tmpdir)
        dag = DAGBuilder(project)
        dag.build()
        downstream = dag.downstream_models("raw")
        assert "cleaned" in downstream
        assert "aggregated" in downstream
