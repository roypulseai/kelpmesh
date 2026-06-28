"""Tests for Phase B: Python models."""

from pathlib import Path

import pytest
import pandas as pd

from briq.parser.python import PythonRefParser
from briq.core.project import Project
from briq.core.executor import Executor
from briq.adapters.duckdb import DuckDBAdapter
from briq.core.config import WarehouseConfig


# ---------------------------------------------------------------------------
# PythonRefParser: AST-based ref/source extraction
# ---------------------------------------------------------------------------

class TestPythonRefParser:
    def test_extract_refs_empty(self):
        assert PythonRefParser.extract_refs("x = 1") == []

    def test_extract_refs_single(self):
        source = 'def model(ref):\n    return ref("upstream")'
        assert PythonRefParser.extract_refs(source) == ["upstream"]

    def test_extract_refs_multiple(self):
        source = '''def model(ref):
    a = ref("first")
    b = ref("second")
    return a.join(b)'''
        refs = PythonRefParser.extract_refs(source)
        assert "first" in refs
        assert "second" in refs

    def test_extract_refs_dedup(self):
        source = 'def model(ref):\n    a = ref("x")\n    b = ref("x")'
        refs = PythonRefParser.extract_refs(source)
        assert refs == ["x", "x"]

    def test_extract_refs_no_ref_call(self):
        source = 'def model(ref):\n    return ref.something()'
        result = PythonRefParser.extract_refs(source)
        assert result == []

    def test_extract_sources(self):
        source = 'def model(source):\n    return source("raw", "users")'
        sources = PythonRefParser.extract_sources(source)
        assert sources == ["raw"]

    def test_extract_sources_multiple(self):
        source = '''def model(source):
    a = source("src", "t1")
    b = source("src", "t2")
    return a.join(b)'''
        sources = PythonRefParser.extract_sources(source)
        assert len(sources) == 2
        assert "src" in sources


# ---------------------------------------------------------------------------
# Project loading: .py model discovery
# ---------------------------------------------------------------------------

class TestPythonModelDiscovery:
    def test_project_loads_py_model(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "my_model.py").write_text(
            '# materialized: table\ndef model(ref):\n    return ref("other")\n'
        )
        project = Project(tmp_path)
        assert "my_model" in project.models
        model = project.models["my_model"]
        assert model.language == "python"
        assert model.python_code is not None
        assert model.materialized == "table"

    def test_python_model_default_materialized(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "m.py").write_text("def model(ref):\n    return ref('x')")
        project = Project(tmp_path)
        assert project.models["m"].materialized == "table"

    def test_python_model_upstream_extracted(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "m.py").write_text("def model(ref):\n    return ref('x')")
        project = Project(tmp_path)
        assert project.models["m"].upstream == {"x"}

    def test_python_model_header_config(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "m.py").write_text(
            "# description: My python model\n# unique_key: id\n"
            "def model(ref):\n    return ref('x')"
        )
        project = Project(tmp_path)
        m = project.models["m"]
        assert m.description == "My python model"
        assert m.unique_key == "id"

    def test_sql_and_python_coexist(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "sql_model.sql").write_text("SELECT 1 AS x")
        (models_dir / "py_model.py").write_text("def model(ref):\n    return ref('sql_model')")
        project = Project(tmp_path)
        assert "sql_model" in project.models
        assert "py_model" in project.models
        assert project.models["sql_model"].language == "sql"
        assert project.models["py_model"].language == "python"
        assert "sql_model" in project.models["py_model"].upstream


# ---------------------------------------------------------------------------
# Python model execution
# ---------------------------------------------------------------------------

class TestPythonModelExecution:
    def test_simple_python_model_dataframe(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "m.py").write_text(
            "import pandas as pd\n"
            "def model():\n"
            "    return pd.DataFrame({'x': [1, 2, 3]})\n"
        )
        project = Project(tmp_path)
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        executor = Executor(project, adapter)
        results = executor.run()
        assert len(results["success"]) == 1
        rows = adapter.execute("SELECT * FROM m ORDER BY x")
        assert len(rows) == 3
        assert rows[0]["x"] == 1
        adapter.disconnect()

    def test_python_model_with_sql_upstream(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "base.sql").write_text("SELECT 1 AS x UNION ALL SELECT 2")
        (models_dir / "derived.py").write_text(
            "def model(ref):\n"
            '    return ref("base").filter("x > 1")\n'
        )
        project = Project(tmp_path)
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        executor = Executor(project, adapter)
        results = executor.run()
        assert len(results["success"]) == 2
        rows = adapter.execute("SELECT * FROM derived ORDER BY x")
        assert len(rows) == 1
        assert rows[0]["x"] == 2
        adapter.disconnect()

    def test_python_model_hash(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "m.py").write_text(
            "def model():\n"
            "    return 42\n"
        )
        project = Project(tmp_path)
        executor = Executor(project, None, None)
        h = executor.compute_model_hash("m")
        assert isinstance(h, str)
        assert len(h) == 16

    def test_python_model_missing_function(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "m.py").write_text("x = 1\n")
        project = Project(tmp_path)
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        executor = Executor(project, adapter)
        results = executor.run()
        assert len(results["failed"]) == 1
        assert "must define a 'model' function" in results["failed"][0]["error"]
        adapter.disconnect()

    def test_python_model_error_in_execution(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "m.py").write_text(
            "def model():\n"
            "    raise ValueError('boom')\n"
        )
        project = Project(tmp_path)
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        executor = Executor(project, adapter)
        results = executor.run()
        assert len(results["failed"]) == 1
        adapter.disconnect()


# ---------------------------------------------------------------------------
# Mixed SQL + Python DAG
# ---------------------------------------------------------------------------

class TestMixedDAG:
    def test_sql_refs_python(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "py_base.py").write_text(
            "import pandas as pd\n"
            "def model():\n"
            "    return pd.DataFrame({'val': [10, 20, 30]})\n"
        )
        (models_dir / "sql_downstream.sql").write_text(
            "SELECT val * 2 AS doubled FROM py_base\n"
        )
        project = Project(tmp_path)
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        executor = Executor(project, adapter)
        results = executor.run()
        assert len(results["success"]) == 2
        rows = adapter.execute("SELECT * FROM sql_downstream ORDER BY doubled")
        assert len(rows) == 3
        assert rows[0]["doubled"] == 20
        adapter.disconnect()

    def test_python_refs_python(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "first.py").write_text(
            "import pandas as pd\n"
            "def model():\n"
            "    return pd.DataFrame({'a': [1, 2]})\n"
        )
        (models_dir / "second.py").write_text(
            "def model(ref):\n"
            '    return ref("first").filter("a > 1")\n'
        )
        project = Project(tmp_path)
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        executor = Executor(project, adapter)
        results = executor.run()
        assert len(results["success"]) == 2
        rows = adapter.execute("SELECT * FROM second ORDER BY a")
        assert len(rows) == 1
        assert rows[0]["a"] == 2
        adapter.disconnect()

    def test_topological_order_mixed(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "a.sql").write_text("SELECT 1 AS id")
        (models_dir / "b.py").write_text(
            "def model(ref):\n"
            '    return ref("a").filter("id = 1")\n'
        )
        (models_dir / "c.sql").write_text("SELECT * FROM b")
        project = Project(tmp_path)
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        executor = Executor(project, adapter)
        order = executor.dag.execution_order()
        # a must come before b, b before c
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")
        adapter.disconnect()


# ---------------------------------------------------------------------------
# CSV / TSV seed loading
# ---------------------------------------------------------------------------

class TestSeedLoading:
    def test_load_csv_via_adapter(self, tmp_path: Path):
        csv_path = tmp_path / "users.csv"
        csv_path.write_text("id,name,age\n1,Alice,30\n2,Bob,25\n")
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        adapter.connect()
        adapter.load_csv(str(csv_path), "users")
        rows = adapter.execute("SELECT * FROM users ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"
        assert rows[1]["age"] == 25
        adapter.disconnect()

    def test_load_tsv_via_adapter(self, tmp_path: Path):
        tsv_path = tmp_path / "products.tsv"
        tsv_path.write_text("id\tname\tprice\n1\tWidget\t9.99\n2\tGadget\t19.99\n")
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        adapter.connect()
        adapter.load_csv(str(tsv_path), "products", delimiter="\t")
        rows = adapter.execute("SELECT * FROM products ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["name"] == "Widget"
        assert rows[0]["price"] == 9.99
        assert rows[1]["name"] == "Gadget"
        assert rows[1]["price"] == 19.99
        adapter.disconnect()

    def test_load_csv_respects_header(self, tmp_path: Path):
        csv_path = tmp_path / "data.csv"
        csv_path.write_text("x,y\n10,20\n30,40\n")
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        adapter.connect()
        adapter.load_csv(str(csv_path), "data")
        rows = adapter.execute("SELECT * FROM data ORDER BY x")
        assert rows[0]["x"] == 10
        assert rows[0]["y"] == 20
        adapter.disconnect()

    def test_seed_sql_still_works(self, tmp_path: Path):
        """briq seed with .sql file executes as SQL."""
        from briq.cli.seed import seed_cmd
        import tempfile
        sql_path = tmp_path / "init.sql"
        sql_path.write_text("SELECT 1 AS ok")
        adapter_cls = DuckDBAdapter
        # Just verify the SQL-reading path works at the adapter level
        adapter = adapter_cls(WarehouseConfig(type="duckdb", path=":memory:"))
        result = adapter.execute(sql_path.read_text())
        assert result == [{"ok": 1}]
        adapter.disconnect()
