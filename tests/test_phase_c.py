"""Tests for Phase C: Semantic layer — sources, exposures, metrics, freshness."""

from pathlib import Path

import pytest

from briq.parser.sql import SQLParser
from briq.parser.python import PythonRefParser
from briq.core.project import Project
from briq.semantic import SourceLoader, ExposureLoader, MetricLoader, BriqMetric
from briq.adapters.duckdb import DuckDBAdapter
from briq.core.config import WarehouseConfig


# ---------------------------------------------------------------------------
# Source() extraction from SQL
# ---------------------------------------------------------------------------

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
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "m.sql").write_text("SELECT * FROM source('raw', 'users')")
        project = Project(tmp_path)
        assert "raw" in project.models["m"].upstream


# ---------------------------------------------------------------------------
# Source() extraction from Python
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Source loader
# ---------------------------------------------------------------------------

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
        assert sources[0].table == "users"
        assert sources[0].freshness is not None
        assert sources[0].freshness.warn_after == "24h"
        assert sources[1].name == "analytics"
        assert sources[1].freshness is None

    def test_load_sources_yaml_extension(self, tmp_path: Path):
        (tmp_path / "sources.yaml").write_text("sources:\n  - name: x\n    table: y\n")
        sources = SourceLoader.load(tmp_path)
        assert len(sources) == 1
        assert sources[0].name == "x"


# ---------------------------------------------------------------------------
# Exposure loader
# ---------------------------------------------------------------------------

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
      - active_users
    description: Executive sales dashboard
  - name: ml_churn
    type: ml
    owner: bob@example.com
    depends_on:
      - user_features
""")
        exposures = ExposureLoader.load(tmp_path)
        assert len(exposures) == 2
        assert exposures[0].name == "dashboard_sales"
        assert exposures[0].type == "dashboard"
        assert "total_revenue" in exposures[0].depends_on
        assert exposures[1].name == "ml_churn"
        assert exposures[1].type == "ml"


# ---------------------------------------------------------------------------
# Metric loader
# ---------------------------------------------------------------------------

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
    description: Sum of all order amounts
    dimensions:
      - status
      - region
  - name: order_count
    model: orders
    label: Order Count
    type: count
""")
        metrics = MetricLoader.load(tmp_path)
        assert len(metrics) == 2
        assert metrics[0].name == "total_revenue"
        assert metrics[0].type == "sum"
        assert metrics[0].sql == "amount"
        assert metrics[0].dimensions == ["status", "region"]
        assert metrics[1].name == "order_count"
        assert metrics[1].type == "count"


# ---------------------------------------------------------------------------
# Metric SQL generation
# ---------------------------------------------------------------------------

class TestMetricSQL:
    def test_count_sql(self):
        m = BriqMetric(name="cnt", model="orders", label="Count", type="count")
        sql = m.generate_sql()
        assert "COUNT(*)" in sql
        assert "FROM orders" in sql

    def test_sum_sql(self):
        m = BriqMetric(name="revenue", model="orders", label="Revenue", type="sum", sql="amount")
        sql = m.generate_sql()
        assert "SUM(amount)" in sql
        assert "FROM orders" in sql

    def test_count_distinct_sql(self):
        m = BriqMetric(name="unique_users", model="events", label="Unique Users", type="count_distinct", sql="user_id")
        sql = m.generate_sql()
        assert "COUNT(DISTINCT user_id)" in sql

    def test_average_sql(self):
        m = BriqMetric(name="avg_price", model="products", label="Avg Price", type="average", sql="price")
        sql = m.generate_sql()
        assert "AVG(price)" in sql

    def test_min_max_sql(self):
        m = BriqMetric(name="min_price", model="products", label="Min Price", type="min", sql="price")
        sql = m.generate_sql()
        assert "MIN(price)" in sql

    def test_with_group_by(self):
        m = BriqMetric(name="cnt", model="orders", label="Count", type="count")
        sql = m.generate_sql(group_by=["status"])
        assert "GROUP BY" in sql
        assert '"status"' in sql or "status" in sql

    def test_with_where(self):
        m = BriqMetric(name="cnt", model="orders", label="Count", type="count")
        sql = m.generate_sql(where="status = 'active'")
        assert "WHERE" in sql
        assert "status = 'active'" in sql

    def test_with_limit(self):
        m = BriqMetric(name="cnt", model="orders", label="Count", type="count")
        sql = m.generate_sql(limit=10)
        assert "LIMIT 10" in sql

    def test_with_filters(self):
        from briq.semantic import MetricFilter
        m = BriqMetric(
            name="revenue", model="orders", label="Revenue",
            type="sum", sql="amount",
            filters=[MetricFilter(field="status", operator="=", value="'completed'")]
        )
        sql = m.generate_sql()
        assert "status = 'completed'" in sql

    def test_expression_type(self):
        m = BriqMetric(name="profit", model="orders", label="Profit", type="expression", sql="revenue - cost")
        sql = m.generate_sql()
        assert "revenue - cost" in sql

    def test_dimensions_included_in_select(self):
        m = BriqMetric(name="cnt", model="orders", label="Count", type="count", dimensions=["status", "region"])
        sql = m.generate_sql(group_by=["status"])
        assert '"region"' in sql
        assert "GROUP BY" in sql


# ---------------------------------------------------------------------------
# Project integration
# ---------------------------------------------------------------------------

class TestProjectSemantic:
    def test_project_loads_sources(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "m.sql").write_text("SELECT 1")
        (tmp_path / "sources.yml").write_text("sources:\n  - name: raw\n    table: users\n")
        project = Project(tmp_path)
        assert "raw" in project.sources
        assert project.sources["raw"].table == "users"

    def test_project_loads_exposures(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "m.sql").write_text("SELECT 1")
        (tmp_path / "exposures.yml").write_text("exposures:\n  - name: dash\n    type: dashboard\n    owner: me\n")
        project = Project(tmp_path)
        assert "dash" in project.exposures

    def test_project_loads_metrics(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "m.sql").write_text("SELECT 1")
        (tmp_path / "metrics.yml").write_text("metrics:\n  - name: cnt\n    model: m\n    label: Count\n    type: count\n")
        project = Project(tmp_path)
        assert "cnt" in project.metrics


# ---------------------------------------------------------------------------
# Metric execution against DuckDB
# ---------------------------------------------------------------------------

class TestMetricExecution:
    def test_count_metric_executes(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "orders.sql").write_text("SELECT 1 AS amount UNION ALL SELECT 2 UNION ALL SELECT 3")
        (tmp_path / "metrics.yml").write_text("metrics:\n  - name: order_cnt\n    model: orders\n    label: Order Count\n    type: count\n")

        project = Project(tmp_path)
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        from briq.core.executor import Executor
        from briq.state.engine import StateEngine
        state = StateEngine(tmp_path)
        executor = Executor(project, adapter, state)
        executor.run()
        adapter.connect()

        metric = project.metrics["order_cnt"]
        sql = metric.generate_sql()
        result = adapter.execute(sql)
        assert len(result) == 1
        assert result[0]["order_cnt"] == 3
        adapter.disconnect()
        state.close()

    def test_sum_metric_executes(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (tmp_path / "briq.yml").write_text("name: test\ntarget_path: target\n")
        (models_dir / "orders.sql").write_text("SELECT 10 AS amount UNION ALL SELECT 20 UNION ALL SELECT 30")
        (tmp_path / "metrics.yml").write_text("metrics:\n  - name: total\n    model: orders\n    label: Total\n    type: sum\n    sql: amount\n")

        project = Project(tmp_path)
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        from briq.core.executor import Executor
        from briq.state.engine import StateEngine
        state = StateEngine(tmp_path)
        executor = Executor(project, adapter, state)
        executor.run()
        adapter.connect()

        metric = project.metrics["total"]
        sql = metric.generate_sql()
        result = adapter.execute(sql)
        assert result[0]["total"] == 60
        adapter.disconnect()
        state.close()
