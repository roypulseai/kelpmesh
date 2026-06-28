"""Phase B acceptance tests — generic tests, snapshots, schema.yml parsing, docs DAG."""

import json
import tempfile
from pathlib import Path
import pytest

from briq.core.schema_yaml import SchemaYaml, _normalise_test
from briq.testing.schema_tests import SchemaTestGenerator
from briq.testing.runner import TestRunner as BriqTestRunner
from briq.adapters.duckdb import DuckDBAdapter
from briq.core.config import WarehouseConfig


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write(path: Path, rel: str, text: str):
    f = path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")


def _adapter(tmp: Path) -> DuckDBAdapter:
    cfg = WarehouseConfig(type="duckdb", path=str(tmp / "test.duckdb"))
    a = DuckDBAdapter(cfg, project_path=str(tmp))
    a.connect()
    return a


# ── SchemaYaml parser ─────────────────────────────────────────────────────────

class TestSchemaYaml:
    def _make_project(self, tmp: Path) -> SchemaYaml:
        _write(tmp, "models/schema.yml", """
models:
  - name: orders
    description: "All orders"
    columns:
      - name: id
        description: "Primary key"
        data_type: INTEGER
        tests:
          - not_null
          - unique
      - name: status
        description: "Order status"
        tests:
          - not_null
          - accepted_values:
              values: [placed, shipped, delivered]
      - name: customer_id
        tests:
          - relationships:
              to: customers
              field: id
""")
        return SchemaYaml(tmp)

    def test_model_description(self, tmp_path):
        schema = self._make_project(tmp_path)
        assert schema.model_description("orders") == "All orders"

    def test_column_descriptions(self, tmp_path):
        schema = self._make_project(tmp_path)
        descs = schema.column_descriptions("orders")
        assert descs["id"] == "Primary key"
        assert descs["status"] == "Order status"

    def test_model_tests_count(self, tmp_path):
        schema = self._make_project(tmp_path)
        tests = schema.model_tests("orders")
        assert len(tests) == 5  # not_null, unique, not_null, accepted_values, relationships

    def test_not_null_test_type(self, tmp_path):
        schema = self._make_project(tmp_path)
        tests = schema.model_tests("orders")
        types = [t["type"] for t in tests]
        assert "not_null" in types
        assert "unique" in types
        assert "accepted_values" in types
        assert "relationships" in types

    def test_accepted_values_config(self, tmp_path):
        schema = self._make_project(tmp_path)
        tests = schema.model_tests("orders")
        av = next(t for t in tests if t["type"] == "accepted_values")
        assert "placed" in av["config"]["values"]

    def test_relationships_config(self, tmp_path):
        schema = self._make_project(tmp_path)
        tests = schema.model_tests("orders")
        rel = next(t for t in tests if t["type"] == "relationships")
        assert rel["config"]["to"] == "customers"
        assert rel["config"]["field"] == "id"

    def test_unknown_model_returns_empty(self, tmp_path):
        schema = self._make_project(tmp_path)
        assert schema.model_tests("nonexistent") == []

    def test_normalise_string_test(self):
        result = _normalise_test("not_null", "id")
        assert result == {"type": "not_null", "column": "id", "config": {}}

    def test_normalise_dict_test(self):
        result = _normalise_test({"accepted_values": {"values": ["a", "b"]}}, "col")
        assert result["type"] == "accepted_values"
        assert result["config"]["values"] == ["a", "b"]

    def test_multiple_schema_files(self, tmp_path):
        _write(tmp_path, "models/orders/schema.yml", """
models:
  - name: orders
    description: "from subfolder"
""")
        _write(tmp_path, "models/customers/models.yml", """
models:
  - name: customers
    description: "customer model"
""")
        schema = SchemaYaml(tmp_path)
        assert schema.model_description("orders") == "from subfolder"
        assert schema.model_description("customers") == "customer model"


# ── SchemaTestGenerator — SQL generation ─────────────────────────────────────

class TestSchemaTestGenerator:
    def _schema(self, tmp: Path) -> SchemaYaml:
        _write(tmp, "models/schema.yml", """
models:
  - name: orders
    columns:
      - name: id
        tests: [not_null, unique]
      - name: status
        tests:
          - accepted_values:
              values: [placed, shipped]
      - name: customer_id
        tests:
          - relationships:
              to: customers
              field: id
""")
        return SchemaYaml(tmp)

    def test_not_null_sql(self, tmp_path):
        gen = SchemaTestGenerator(self._schema(tmp_path))
        tests = gen.tests_for_model("orders")
        nn = next(t for t in tests if "not_null" in t["name"])
        assert "IS NULL" in nn["sql"]
        assert '"orders"' in nn["sql"]

    def test_unique_sql(self, tmp_path):
        gen = SchemaTestGenerator(self._schema(tmp_path))
        tests = gen.tests_for_model("orders")
        uq = next(t for t in tests if "unique" in t["name"])
        assert "HAVING COUNT(*)" in uq["sql"]

    def test_accepted_values_sql(self, tmp_path):
        gen = SchemaTestGenerator(self._schema(tmp_path))
        tests = gen.tests_for_model("orders")
        av = next(t for t in tests if "accepted_values" in t["name"])
        assert "NOT IN" in av["sql"]
        assert "'placed'" in av["sql"]
        assert "'shipped'" in av["sql"]

    def test_relationships_sql(self, tmp_path):
        gen = SchemaTestGenerator(self._schema(tmp_path))
        tests = gen.tests_for_model("orders")
        rel = next(t for t in tests if "relationships" in t["name"])
        assert "NOT IN" in rel["sql"]
        assert '"customers"' in rel["sql"]

    def test_all_tests_spans_all_models(self, tmp_path):
        _write(tmp_path, "models/schema.yml", """
models:
  - name: a
    columns:
      - name: id
        tests: [not_null]
  - name: b
    columns:
      - name: id
        tests: [unique]
""")
        schema = SchemaYaml(tmp_path)
        gen = SchemaTestGenerator(schema)
        all_t = gen.all_tests()
        names = [t["name"] for t in all_t]
        assert any("a." in n for n in names)
        assert any("b." in n for n in names)


# ── Generic tests run end-to-end ──────────────────────────────────────────────

class TestGenericTestsEndToEnd:
    def test_not_null_passes(self, tmp_path):
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE orders AS SELECT 1 AS id, 'placed' AS status")
        _write(tmp_path, "models/schema.yml", """
models:
  - name: orders
    columns:
      - name: id
        tests: [not_null]
""")
        schema = SchemaYaml(tmp_path)
        schema_tests = SchemaTestGenerator(schema).all_tests()
        runner = BriqTestRunner(adapter, schema_tests=schema_tests)
        results = runner.run_all(tmp_path / "tests")
        assert any(r["name"] == "orders.id.not_null" and r["passed"] for r in results)
        adapter.disconnect()

    def test_not_null_fails(self, tmp_path):
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE orders AS SELECT NULL AS id")
        _write(tmp_path, "models/schema.yml", """
models:
  - name: orders
    columns:
      - name: id
        tests: [not_null]
""")
        schema = SchemaYaml(tmp_path)
        schema_tests = SchemaTestGenerator(schema).all_tests()
        runner = BriqTestRunner(adapter, schema_tests=schema_tests)
        results = runner.run_all(tmp_path / "tests")
        nn = next(r for r in results if "not_null" in r["name"])
        assert not nn["passed"]
        assert nn["failures"] == 1
        adapter.disconnect()

    def test_unique_fails_on_duplicate(self, tmp_path):
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE orders AS SELECT * FROM (VALUES (1), (1), (2)) t(id)")
        _write(tmp_path, "models/schema.yml", """
models:
  - name: orders
    columns:
      - name: id
        tests: [unique]
""")
        schema = SchemaYaml(tmp_path)
        schema_tests = SchemaTestGenerator(schema).all_tests()
        runner = BriqTestRunner(adapter, schema_tests=schema_tests)
        results = runner.run_all(tmp_path / "tests")
        uq = next(r for r in results if "unique" in r["name"])
        assert not uq["passed"]
        adapter.disconnect()

    def test_accepted_values_passes(self, tmp_path):
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE orders AS SELECT 'placed' AS status")
        _write(tmp_path, "models/schema.yml", """
models:
  - name: orders
    columns:
      - name: status
        tests:
          - accepted_values:
              values: [placed, shipped, delivered]
""")
        schema = SchemaYaml(tmp_path)
        schema_tests = SchemaTestGenerator(schema).all_tests()
        runner = BriqTestRunner(adapter, schema_tests=schema_tests)
        results = runner.run_all(tmp_path / "tests")
        av = next(r for r in results if "accepted_values" in r["name"])
        assert av["passed"]
        adapter.disconnect()

    def test_relationships_passes(self, tmp_path):
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE customers AS SELECT 1 AS id")
        adapter.execute("CREATE TABLE orders AS SELECT 1 AS customer_id")
        _write(tmp_path, "models/schema.yml", """
models:
  - name: orders
    columns:
      - name: customer_id
        tests:
          - relationships:
              to: customers
              field: id
""")
        schema = SchemaYaml(tmp_path)
        schema_tests = SchemaTestGenerator(schema).all_tests()
        runner = BriqTestRunner(adapter, schema_tests=schema_tests)
        results = runner.run_all(tmp_path / "tests")
        rel = next(r for r in results if "relationships" in r["name"])
        assert rel["passed"]
        adapter.disconnect()


# ── Snapshots ────────────────────────────────────────────────────────────────

class TestSnapshots:
    def test_initial_snapshot_creates_table(self, tmp_path):
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE source AS SELECT 1 AS id, 'alice' AS name, '2025-01-01'::TIMESTAMP AS updated_at")
        adapter.execute_snapshot(
            sql="SELECT * FROM source",
            table_name="snap_users",
            unique_key="id",
            strategy="timestamp",
            updated_at="updated_at",
        )
        rows = adapter.execute("SELECT * FROM snap_users")
        assert len(rows) == 1
        assert rows[0]["_is_current"] is True
        assert rows[0]["_valid_to"] is None
        adapter.disconnect()

    def test_snapshot_scd2_on_change(self, tmp_path):
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE source AS SELECT 1 AS id, 'alice' AS name, '2025-01-01 00:00:00'::TIMESTAMP AS updated_at")
        adapter.execute_snapshot("SELECT * FROM source", "snap_users", "id", "timestamp", "updated_at")

        # Update source to simulate a change
        adapter.execute("UPDATE source SET name = 'ALICE', updated_at = '2025-06-01 00:00:00'")
        adapter.execute_snapshot("SELECT * FROM source", "snap_users", "id", "timestamp", "updated_at")

        rows = adapter.execute("SELECT * FROM snap_users ORDER BY _valid_from")
        assert len(rows) == 2
        old = rows[0]
        new = rows[1]
        assert old["_is_current"] is False
        assert old["_valid_to"] is not None
        assert new["_is_current"] is True
        assert new["name"] == "ALICE"
        adapter.disconnect()

    def test_snapshot_no_change_no_new_row(self, tmp_path):
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE source AS SELECT 1 AS id, 'alice' AS name, '2025-01-01'::TIMESTAMP AS updated_at")
        adapter.execute_snapshot("SELECT * FROM source", "snap_users", "id", "timestamp", "updated_at")
        adapter.execute_snapshot("SELECT * FROM source", "snap_users", "id", "timestamp", "updated_at")
        rows = adapter.execute("SELECT * FROM snap_users")
        assert len(rows) == 1
        adapter.disconnect()


# ── Docs generator ────────────────────────────────────────────────────────────

class TestDocsGenerator:
    def test_docs_generates_html_and_manifest(self, tmp_path):
        from typer.testing import CliRunner
        from briq.cli.main import app
        runner = CliRunner()

        _write(tmp_path, "briq.yml",
               "name: test\nwarehouse:\n  type: duckdb\n  path: target/test.duckdb\n")
        _write(tmp_path, "models/orders.sql", "SELECT 1 AS id, 'placed' AS status")
        _write(tmp_path, "models/schema.yml", """
models:
  - name: orders
    description: "Order records"
    columns:
      - name: id
        description: "Primary key"
      - name: status
        description: "Order status"
""")
        r = runner.invoke(app, ["docs", "-p", str(tmp_path)], catch_exceptions=False)
        assert r.exit_code == 0, r.output
        html = (tmp_path / "target" / "docs" / "index.html").read_text()
        manifest = json.loads((tmp_path / "target" / "docs" / "manifest.json").read_text())
        assert "Order records" in html
        assert "dag-canvas" in html          # interactive DAG present
        assert "Primary key" in html         # YAML description merged
        assert manifest["models"][0]["description"] == "Order records"


# ── Model contracts ───────────────────────────────────────────────────────────

class TestModelContracts:
    def _schema_with_contract(self, tmp: Path) -> "SchemaYaml":
        _write(tmp, "models/schema.yml", """
models:
  - name: orders
    contract:
      enforced: true
    columns:
      - name: id
        data_type: INTEGER
      - name: status
        data_type: VARCHAR
""")
        return SchemaYaml(tmp)

    def test_contract_passes_correct_schema(self, tmp_path):
        from briq.core.contracts import check_contract
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE orders AS SELECT 1::INTEGER AS id, 'placed'::VARCHAR AS status")
        schema = self._schema_with_contract(tmp_path)
        result = check_contract("orders", adapter, schema)
        assert result.passed, [str(v) for v in result.violations]
        adapter.disconnect()

    def test_contract_fails_missing_column(self, tmp_path):
        from briq.core.contracts import check_contract
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE orders AS SELECT 1::INTEGER AS id")
        schema = self._schema_with_contract(tmp_path)
        result = check_contract("orders", adapter, schema)
        assert not result.passed
        kinds = [v.kind for v in result.violations]
        assert "missing_column" in kinds
        adapter.disconnect()

    def test_contract_fails_type_mismatch(self, tmp_path):
        from briq.core.contracts import check_contract
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE orders AS SELECT 'x' AS id, 'placed' AS status")
        schema = self._schema_with_contract(tmp_path)
        result = check_contract("orders", adapter, schema)
        assert not result.passed
        kinds = [v.kind for v in result.violations]
        assert "type_mismatch" in kinds
        adapter.disconnect()

    def test_no_contract_always_passes(self, tmp_path):
        from briq.core.contracts import check_contract
        _write(tmp_path, "models/schema.yml", """
models:
  - name: orders
    columns:
      - name: id
""")
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE orders AS SELECT 1 AS id")
        schema = SchemaYaml(tmp_path)
        result = check_contract("orders", adapter, schema)
        assert result.passed
        adapter.disconnect()

    def test_constrained_columns_flags_extra(self, tmp_path):
        from briq.core.contracts import check_contract
        _write(tmp_path, "models/schema.yml", """
models:
  - name: orders
    contract:
      enforced: true
      constrained_columns: true
    columns:
      - name: id
        data_type: INTEGER
""")
        adapter = _adapter(tmp_path)
        adapter.execute("CREATE TABLE orders AS SELECT 1::INTEGER AS id, 'x' AS extra_col")
        schema = SchemaYaml(tmp_path)
        result = check_contract("orders", adapter, schema)
        assert not result.passed
        kinds = [v.kind for v in result.violations]
        assert "extra_column" in kinds
        adapter.disconnect()


# ── briq generate ─────────────────────────────────────────────────────────────

class TestGenerate:
    def test_generate_creates_staging_model(self, tmp_path):
        from typer.testing import CliRunner
        from briq.cli.main import app
        runner = CliRunner()

        _write(tmp_path, "briq.yml",
               "name: test\nwarehouse:\n  type: duckdb\n  path: target/test.duckdb\n")
        # Pre-create the source table so introspection works
        import duckdb
        db_path = str(tmp_path / "target" / "test.duckdb")
        (tmp_path / "target").mkdir(exist_ok=True)
        conn = duckdb.connect(db_path)
        conn.execute("CREATE TABLE orders AS SELECT 1::INTEGER AS id, 'placed'::VARCHAR AS status")
        conn.close()

        r = runner.invoke(app, ["generate", "orders", "-p", str(tmp_path)], catch_exceptions=False)
        assert r.exit_code == 0, r.output
        model_file = tmp_path / "models" / "staging" / "stg_orders.sql"
        assert model_file.exists()
        sql = model_file.read_text()
        assert "id" in sql
        assert "status" in sql

    def test_generate_creates_schema_yml(self, tmp_path):
        from typer.testing import CliRunner
        from briq.cli.main import app
        runner = CliRunner()

        _write(tmp_path, "briq.yml",
               "name: test\nwarehouse:\n  type: duckdb\n  path: target/test.duckdb\n")
        import duckdb
        db_path = str(tmp_path / "target" / "test.duckdb")
        (tmp_path / "target").mkdir(exist_ok=True)
        conn = duckdb.connect(db_path)
        conn.execute("CREATE TABLE orders AS SELECT 1::INTEGER AS id")
        conn.close()

        r = runner.invoke(app, ["generate", "orders", "--schema", "-p", str(tmp_path)], catch_exceptions=False)
        assert r.exit_code == 0, r.output
        schema_file = tmp_path / "models" / "staging" / "schema.yml"
        assert schema_file.exists()
        content = schema_file.read_text()
        assert "stg_orders" in content
        assert "INTEGER" in content
