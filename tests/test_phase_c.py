"""Phase C acceptance tests — plan, env isolation, run history, anomaly detection, freshness, alerting."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
import pytest

from kelpmesh.adapters.duckdb import DuckDBAdapter
from kelpmesh.core.config import WarehouseConfig


def _write(path: Path, rel: str, text: str):
    f = path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")


def _adapter(tmp: Path) -> DuckDBAdapter:
    cfg = WarehouseConfig(type="duckdb", path=str(tmp / "test.duckdb"))
    a = DuckDBAdapter(cfg, project_path=str(tmp))
    a.connect()
    return a


def _make_project(tmp: Path):
    _write(tmp, "kelpmesh.yml",
           "name: testproj\nwarehouse:\n  type: duckdb\n  path: target/test.duckdb\n")
    _write(tmp, "models/customers.sql", "SELECT 1 AS id, 'alice' AS name")
    _write(tmp, "models/orders.sql",
           "SELECT 1 AS id, 1 AS customer_id FROM customers")


# ── kelpmesh plan ────────────────────────────────────────────────────────────────

class TestPlan:
    def test_plan_shows_all_models(self, tmp_path):
        from typer.testing import CliRunner
        from kelpmesh.cli.main import app
        _make_project(tmp_path)
        runner = CliRunner()
        r = runner.invoke(app, ["plan", "-p", str(tmp_path)], catch_exceptions=False)
        assert r.exit_code == 0, r.output
        # Rich may truncate long names in narrow terminals; check prefix
        assert "custome" in r.output
        assert "orders" in r.output

    def test_plan_shows_new_for_unrun_models(self, tmp_path):
        from typer.testing import CliRunner
        from kelpmesh.cli.main import app
        _make_project(tmp_path)
        runner = CliRunner()
        r = runner.invoke(app, ["plan", "-p", str(tmp_path)], catch_exceptions=False)
        assert r.exit_code == 0
        assert "NEW" in r.output

    def test_plan_shows_skip_after_run(self, tmp_path):
        from typer.testing import CliRunner
        from kelpmesh.cli.main import app
        _make_project(tmp_path)
        runner = CliRunner()
        runner.invoke(app, ["run", "-p", str(tmp_path)], catch_exceptions=False)
        r = runner.invoke(app, ["plan", "-p", str(tmp_path)], catch_exceptions=False)
        assert r.exit_code == 0
        assert "SKIP" in r.output

    def test_plan_json_output(self, tmp_path):
        from typer.testing import CliRunner
        from kelpmesh.cli.main import app
        _make_project(tmp_path)
        runner = CliRunner()
        r = runner.invoke(app, ["plan", "--json", "-p", str(tmp_path)], catch_exceptions=False)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list)
        assert all("name" in row and "action" in row for row in data)

    def test_plan_with_env_prefix(self, tmp_path):
        from typer.testing import CliRunner
        from kelpmesh.cli.main import app
        _make_project(tmp_path)
        runner = CliRunner()
        r = runner.invoke(app, ["plan", "--env", "dev", "--json", "-p", str(tmp_path)], catch_exceptions=False)
        assert r.exit_code == 0
        data = json.loads(r.output)
        for row in data:
            assert row["table_name"].startswith("dev_"), f"Expected dev_ prefix, got {row['table_name']}"


# ── Environment isolation ─────────────────────────────────────────────────────

class TestEnvIsolation:
    def test_env_creates_prefixed_tables(self, tmp_path):
        from kelpmesh.core.project import Project
        from kelpmesh.core.executor import Executor
        from kelpmesh.state.engine import StateEngine
        _make_project(tmp_path)
        project = Project(tmp_path)
        cfg = WarehouseConfig(type="duckdb", path=str(tmp_path / "target" / "test.duckdb"))
        adapter = DuckDBAdapter(cfg, project_path=str(tmp_path))
        adapter.connect()
        state = StateEngine(tmp_path)
        executor = Executor(project, adapter, state, threads=1, env="dev")
        executor.run()
        tables = adapter.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'dev_%'"
        )
        table_names = {r["table_name"] for r in tables}
        assert "dev_customers" in table_names
        assert "dev_orders" in table_names
        adapter.disconnect()
        state.close()

    def test_no_env_uses_bare_names(self, tmp_path):
        from kelpmesh.core.project import Project
        from kelpmesh.core.executor import Executor
        from kelpmesh.state.engine import StateEngine
        _make_project(tmp_path)
        project = Project(tmp_path)
        cfg = WarehouseConfig(type="duckdb", path=str(tmp_path / "target" / "test.duckdb"))
        adapter = DuckDBAdapter(cfg, project_path=str(tmp_path))
        adapter.connect()
        state = StateEngine(tmp_path)
        executor = Executor(project, adapter, state, threads=1)
        executor.run()
        tables = adapter.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'customers'"
        )
        assert len(tables) == 1
        adapter.disconnect()
        state.close()


# ── Run history ───────────────────────────────────────────────────────────────

class TestRunHistory:
    def test_history_records_runs(self, tmp_path):
        from kelpmesh.observability.history import RunHistory
        h = RunHistory(tmp_path)
        h.record("run1", "orders", "success", datetime.now(), 1.23, row_count=100)
        h.record("run1", "customers", "success", datetime.now(), 0.5, row_count=50)
        rows = h.get_history()
        assert len(rows) == 2
        h.close()

    def test_history_filter_by_model(self, tmp_path):
        from kelpmesh.observability.history import RunHistory
        h = RunHistory(tmp_path)
        h.record("r1", "orders", "success", datetime.now(), 1.0, row_count=10)
        h.record("r1", "customers", "success", datetime.now(), 1.0, row_count=5)
        rows = h.get_history(model_name="orders")
        assert len(rows) == 1
        assert rows[0]["model_name"] == "orders"
        h.close()

    def test_history_filter_by_env(self, tmp_path):
        from kelpmesh.observability.history import RunHistory
        h = RunHistory(tmp_path)
        h.record("r1", "orders", "success", datetime.now(), 1.0, row_count=10, env="prod")
        h.record("r2", "orders", "success", datetime.now(), 1.0, row_count=10, env="dev")
        prod_rows = h.get_history(env="prod")
        assert all(r["env"] == "prod" for r in prod_rows)
        h.close()

    def test_rolling_row_counts(self, tmp_path):
        from kelpmesh.observability.history import RunHistory
        h = RunHistory(tmp_path)
        for i, count in enumerate([100, 110, 105, 95, 102]):
            h.record(f"r{i}", "orders", "success", datetime.now(), 1.0, row_count=count)
        counts = h.rolling_row_counts("orders", n=5)
        assert len(counts) == 5
        assert counts[-1] == 102  # most recent last
        h.close()

    def test_history_cli_shows_output(self, tmp_path):
        from typer.testing import CliRunner
        from kelpmesh.cli.main import app
        from kelpmesh.observability.history import RunHistory
        _make_project(tmp_path)
        h = RunHistory(tmp_path)
        h.record("run1", "orders", "success", datetime.now(), 1.5, row_count=42)
        h.close()
        runner = CliRunner()
        r = runner.invoke(app, ["history", "-p", str(tmp_path)], catch_exceptions=False)
        assert r.exit_code == 0
        assert "orders" in r.output


# ── Anomaly detection ─────────────────────────────────────────────────────────

class TestAnomalyDetection:
    def test_no_alert_within_threshold(self):
        from kelpmesh.observability.anomaly import check_row_count_anomaly
        history = [100, 102, 98, 100, 101, 99, 100]
        alert = check_row_count_anomaly("orders", 103, history)
        assert alert is None

    def test_warn_on_moderate_deviation(self):
        from kelpmesh.observability.anomaly import check_row_count_anomaly
        history = [100, 100, 100, 100, 100, 100, 100]
        alert = check_row_count_anomaly("orders", 140, history, warn_threshold=0.30, error_threshold=0.70)
        assert alert is not None
        assert alert.severity == "warn"
        assert alert.deviation_pct > 0

    def test_error_on_large_deviation(self):
        from kelpmesh.observability.anomaly import check_row_count_anomaly
        history = [100, 100, 100, 100, 100, 100, 100]
        alert = check_row_count_anomaly("orders", 200, history, warn_threshold=0.30, error_threshold=0.70)
        assert alert is not None
        assert alert.severity == "error"

    def test_no_alert_with_fewer_than_3_history(self):
        from kelpmesh.observability.anomaly import check_row_count_anomaly
        alert = check_row_count_anomaly("orders", 0, [100, 100])
        assert alert is None

    def test_alert_str_contains_model_name(self):
        from kelpmesh.observability.anomaly import check_row_count_anomaly
        history = [100] * 7
        alert = check_row_count_anomaly("my_model", 200, history)
        assert "my_model" in str(alert)

    def test_negative_deviation_also_triggers(self):
        from kelpmesh.observability.anomaly import check_row_count_anomaly
        history = [100, 100, 100, 100, 100, 100, 100]
        alert = check_row_count_anomaly("orders", 10, history)
        assert alert is not None
        assert alert.deviation_pct < 0


# ── Alerts ────────────────────────────────────────────────────────────────────

class TestAlerts:
    def test_run_summary_has_failures(self):
        from kelpmesh.observability.alerts import RunSummary
        s = RunSummary(
            project_name="test",
            env="prod",
            succeeded=["a"],
            skipped=[],
            failed=[{"name": "b", "error": "oops"}],
            anomalies=[],
            elapsed_s=1.0,
        )
        assert s.has_failures

    def test_run_summary_no_failures(self):
        from kelpmesh.observability.alerts import RunSummary
        s = RunSummary("test", "dev", ["a", "b"], [], [], [], 1.0)
        assert not s.has_failures

    def test_slack_alert_skips_on_no_failure(self):
        from kelpmesh.observability.alerts import RunSummary, send_slack_alert
        s = RunSummary("test", "dev", ["a"], [], [], [], 1.0)
        result = send_slack_alert("http://localhost/no-such-webhook", s)
        assert result is True  # no failures → skips HTTP call entirely

    def test_webhook_payload_structure(self):
        from kelpmesh.observability.alerts import RunSummary
        s = RunSummary(
            project_name="myproject",
            env="prod",
            succeeded=["a"],
            skipped=[],
            failed=[{"name": "b", "error": "timeout"}],
            anomalies=["b — row_count deviated +80%"],
            elapsed_s=5.2,
        )
        assert s.has_failures
        assert s.has_anomalies
        assert s.failed[0]["name"] == "b"


# ── kelpmesh run --env integration ────────────────────────────────────────────────

class TestRunWithEnv:
    def test_run_env_flag_creates_prefixed_tables(self, tmp_path):
        from typer.testing import CliRunner
        from kelpmesh.cli.main import app
        _make_project(tmp_path)
        runner = CliRunner()
        r = runner.invoke(app, ["run", "--env", "staging", "-p", str(tmp_path)], catch_exceptions=False)
        assert r.exit_code == 0, r.output
        import duckdb
        conn = duckdb.connect(str(tmp_path / "target" / "test.duckdb"))
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'staging_%'"
        ).fetchall()
        conn.close()
        names = {t[0] for t in tables}
        assert "staging_customers" in names

    def test_history_recorded_after_run(self, tmp_path):
        from typer.testing import CliRunner
        from kelpmesh.cli.main import app
        from kelpmesh.observability.history import RunHistory
        _make_project(tmp_path)
        runner = CliRunner()
        runner.invoke(app, ["run", "-p", str(tmp_path)], catch_exceptions=False)
        h = RunHistory(tmp_path)
        rows = h.get_history()
        h.close()
        assert len(rows) >= 2  # customers + orders
        assert all(r["status"] == "success" for r in rows)


# ── Semantic layer tests (pre-existing) ───────────────────────────────────────

from kelpmesh.parser.sql import SQLParser
from kelpmesh.parser.python import PythonRefParser
from kelpmesh.core.project import Project
from kelpmesh.semantic import SourceLoader, ExposureLoader, MetricLoader, KelpMeshMetric


class TestSQLSourceDetection:
    def test_extract_source_refs_empty(self):
        assert SQLParser().extract_source_references("SELECT 1") == []

    def test_extract_source_refs_single(self):
        sql = "SELECT * FROM source('raw', 'users')"
        assert SQLParser().extract_source_references(sql) == ["raw"]

    def test_extract_source_refs_multiple(self):
        sql = "SELECT * FROM source('raw', 'users') JOIN source('raw', 'orders') USING (id)"
        refs = SQLParser().extract_source_references(sql)
        assert "raw" in refs

    def test_source_added_to_upstream(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "kelpmesh.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "m.sql").write_text("SELECT * FROM source('raw', 'users')")
        project = Project(tmp_path)
        assert "raw" in project.models["m"].upstream


class TestPythonSourceDetection:
    def test_extract_sources_empty(self):
        assert PythonRefParser.extract_sources("x = 1") == []

    def test_extract_sources_single(self):
        source = 'def model(source):\n    return source("raw", "users")'
        assert PythonRefParser.extract_sources(source) == ["raw"]

    def test_extract_sources_multiple(self):
        source = 'def model(source):\n    a = source("src", "t1")\n    b = source("src", "t2")\n    return a'
        sources = PythonRefParser.extract_sources(source)
        assert len(sources) == 2
        assert "src" in sources


class TestSourceLoader:
    def test_no_sources_file(self, tmp_path: Path):
        assert SourceLoader.load(tmp_path) == []

    def test_load_sources(self, tmp_path: Path):
        (tmp_path / "sources.yml").write_text("""
sources:
  - name: raw
    table: users
    loader: manual
    freshness:
      warn_after: 24h
      error_after: 72h
  - name: analytics
    table: events
    description: Event data
""")
        sources = SourceLoader.load(tmp_path)
        assert len(sources) == 2
        assert sources[0].name == "raw"
        assert sources[0].freshness is not None
        assert sources[1].name == "analytics"
        assert sources[1].freshness is None

    def test_load_sources_yaml_extension(self, tmp_path: Path):
        (tmp_path / "sources.yaml").write_text("sources:\n  - name: x\n    table: y\n")
        sources = SourceLoader.load(tmp_path)
        assert len(sources) == 1


class TestExposureLoader:
    def test_no_exposures_file(self, tmp_path: Path):
        assert ExposureLoader.load(tmp_path) == []

    def test_load_exposures(self, tmp_path: Path):
        (tmp_path / "exposures.yml").write_text("""
exposures:
  - name: dashboard_sales
    type: dashboard
    url: https://looker.example.com/dash/1
    owner: alice@example.com
    depends_on:
      - total_revenue
  - name: ml_churn
    type: ml
    owner: bob@example.com
    depends_on:
      - user_features
""")
        exposures = ExposureLoader.load(tmp_path)
        assert len(exposures) == 2
        assert exposures[0].name == "dashboard_sales"
        assert "total_revenue" in exposures[0].depends_on


class TestMetricLoader:
    def test_no_metrics_file(self, tmp_path: Path):
        assert MetricLoader.load(tmp_path) == []

    def test_load_metrics(self, tmp_path: Path):
        (tmp_path / "metrics.yml").write_text("""
metrics:
  - name: total_revenue
    model: orders
    label: Total Revenue
    type: sum
    sql: amount
    dimensions: [status, region]
  - name: order_count
    model: orders
    label: Order Count
    type: count
""")
        metrics = MetricLoader.load(tmp_path)
        assert len(metrics) == 2
        assert metrics[0].name == "total_revenue"
        assert metrics[0].dimensions == ["status", "region"]


class TestMetricSQL:
    def test_count_sql(self):
        m = KelpMeshMetric(name="cnt", model="orders", label="Count", type="count")
        assert "COUNT(*)" in m.generate_sql()

    def test_sum_sql(self):
        m = KelpMeshMetric(name="revenue", model="orders", label="Revenue", type="sum", sql="amount")
        assert "SUM(amount)" in m.generate_sql()

    def test_count_distinct_sql(self):
        m = KelpMeshMetric(name="uu", model="events", label="UU", type="count_distinct", sql="user_id")
        assert "COUNT(DISTINCT user_id)" in m.generate_sql()

    def test_average_sql(self):
        m = KelpMeshMetric(name="avg", model="products", label="Avg", type="average", sql="price")
        assert "AVG(price)" in m.generate_sql()

    def test_with_group_by(self):
        m = KelpMeshMetric(name="cnt", model="orders", label="Count", type="count")
        assert "GROUP BY" in m.generate_sql(group_by=["status"])

    def test_with_where(self):
        m = KelpMeshMetric(name="cnt", model="orders", label="Count", type="count")
        assert "WHERE" in m.generate_sql(where="status = 'active'")

    def test_with_limit(self):
        m = KelpMeshMetric(name="cnt", model="orders", label="Count", type="count")
        assert "LIMIT 10" in m.generate_sql(limit=10)

    def test_expression_type(self):
        m = KelpMeshMetric(name="profit", model="orders", label="Profit", type="expression", sql="revenue - cost")
        assert "revenue - cost" in m.generate_sql()


class TestProjectSemantic:
    def test_project_loads_sources(self, tmp_path: Path):
        (tmp_path / "models").mkdir()
        (tmp_path / "kelpmesh.yml").write_text("name: test\ntarget_path: target\n")
        (tmp_path / "models" / "m.sql").write_text("SELECT 1")
        (tmp_path / "sources.yml").write_text("sources:\n  - name: raw\n    table: users\n")
        project = Project(tmp_path)
        assert "raw" in project.sources

    def test_project_loads_exposures(self, tmp_path: Path):
        (tmp_path / "models").mkdir()
        (tmp_path / "kelpmesh.yml").write_text("name: test\ntarget_path: target\n")
        (tmp_path / "models" / "m.sql").write_text("SELECT 1")
        (tmp_path / "exposures.yml").write_text("exposures:\n  - name: dash\n    type: dashboard\n    owner: me\n")
        project = Project(tmp_path)
        assert "dash" in project.exposures

    def test_project_loads_metrics(self, tmp_path: Path):
        (tmp_path / "models").mkdir()
        (tmp_path / "kelpmesh.yml").write_text("name: test\ntarget_path: target\n")
        (tmp_path / "models" / "m.sql").write_text("SELECT 1")
        (tmp_path / "metrics.yml").write_text("metrics:\n  - name: cnt\n    model: m\n    label: Count\n    type: count\n")
        project = Project(tmp_path)
        assert "cnt" in project.metrics
