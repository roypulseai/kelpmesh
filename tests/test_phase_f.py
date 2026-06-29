"""Phase F — Semantic Layer BI Exporters tests."""

from __future__ import annotations
import json
from pathlib import Path
import pytest
from kelpmesh.semantic import KelpMeshMetric, KelpMeshSource, KelpMeshExposure, MetricFilter, MetricLoader


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_metrics() -> list[KelpMeshMetric]:
    return [
        KelpMeshMetric(
            name="total_orders",
            model="fct_orders",
            label="Total Orders",
            type="count",
            description="Number of orders",
            dimensions=["status", "customer_id"],
            tags=["finance"],
        ),
        KelpMeshMetric(
            name="total_revenue",
            model="fct_orders",
            label="Total Revenue",
            type="sum",
            sql="amount",
            description="Sum of order amounts",
            dimensions=["status"],
            format_string="$#,##0.00",
            tags=["finance"],
        ),
        KelpMeshMetric(
            name="avg_order_value",
            model="fct_orders",
            label="Average Order Value",
            type="average",
            sql="amount",
            description="Average order value",
            dimensions=["status"],
            format_string="$#,##0.00",
        ),
    ]


@pytest.fixture
def ratio_metric() -> KelpMeshMetric:
    return KelpMeshMetric(
        name="conversion_rate",
        model="fct_events",
        label="Conversion Rate",
        type="ratio",
        numerator="converted",
        denominator="total_sessions",
        description="Sessions that converted",
        format_string="0.00%",
    )


@pytest.fixture
def derived_metric() -> KelpMeshMetric:
    return KelpMeshMetric(
        name="revenue_per_order",
        model="fct_orders",
        label="Revenue Per Order",
        type="derived",
        expression="{{total_revenue}} / {{total_orders}}",
        description="Revenue divided by order count",
    )


@pytest.fixture
def all_metrics(simple_metrics, ratio_metric, derived_metric) -> list[KelpMeshMetric]:
    return simple_metrics + [ratio_metric, derived_metric]


@pytest.fixture
def sources() -> list[KelpMeshSource]:
    return [
        KelpMeshSource(name="raw_orders", table="raw.orders", description="Raw order data"),
    ]


@pytest.fixture
def exposures() -> list[KelpMeshExposure]:
    return [
        KelpMeshExposure(name="orders_dashboard", type="dashboard", owner="roypulse.ai@gmail.com",
                     depends_on=["fct_orders"]),
    ]


# ---------------------------------------------------------------------------
# KelpMeshMetric extensions
# ---------------------------------------------------------------------------

class TestKelpMeshMetricExtensions:
    def test_ratio_fields(self, ratio_metric):
        assert ratio_metric.type == "ratio"
        assert ratio_metric.numerator == "converted"
        assert ratio_metric.denominator == "total_sessions"

    def test_derived_fields(self, derived_metric):
        assert derived_metric.type == "derived"
        assert "{{total_revenue}}" in derived_metric.expression

    def test_format_string(self, simple_metrics):
        rev = next(m for m in simple_metrics if m.name == "total_revenue")
        assert rev.format_string == "$#,##0.00"

    def test_tags(self, simple_metrics):
        assert "finance" in simple_metrics[0].tags

    def test_generate_sql_count(self, simple_metrics):
        sql = simple_metrics[0].generate_sql()
        assert "COUNT(*)" in sql
        assert "fct_orders" in sql

    def test_generate_sql_sum(self, simple_metrics):
        sql = simple_metrics[1].generate_sql()
        assert "SUM(amount)" in sql

    def test_generate_sql_with_group_by(self, simple_metrics):
        sql = simple_metrics[0].generate_sql(group_by=["status"])
        assert "GROUP BY" in sql

    def test_generate_sql_with_limit(self, simple_metrics):
        sql = simple_metrics[0].generate_sql(limit=100)
        assert "LIMIT 100" in sql


# ---------------------------------------------------------------------------
# MetricLoader YAML
# ---------------------------------------------------------------------------

class TestMetricLoader:
    def test_load_ratio_from_yaml(self, tmp_path):
        (tmp_path / "metrics.yml").write_text("""
metrics:
  - name: conv_rate
    label: Conversion Rate
    type: ratio
    numerator: conversions
    denominator: sessions
    format_string: "0.00%"
    tags: [marketing]
""", encoding="utf-8")
        metrics = MetricLoader.load(tmp_path)
        assert len(metrics) == 1
        m = metrics[0]
        assert m.type == "ratio"
        assert m.numerator == "conversions"
        assert m.denominator == "sessions"
        assert m.format_string == "0.00%"
        assert "marketing" in m.tags

    def test_load_derived_from_yaml(self, tmp_path):
        (tmp_path / "metrics.yml").write_text("""
metrics:
  - name: rev_per_order
    label: Revenue Per Order
    type: derived
    expression: "{{total_revenue}} / {{total_orders}}"
""", encoding="utf-8")
        metrics = MetricLoader.load(tmp_path)
        assert metrics[0].type == "derived"
        assert "{{total_revenue}}" in metrics[0].expression


# ---------------------------------------------------------------------------
# ExportResult
# ---------------------------------------------------------------------------

class TestExportResult:
    def test_write_to(self, tmp_path, simple_metrics):
        from kelpmesh.semantic.exporters.base import ExportResult
        result = ExportResult(
            files={"subdir/output.txt": "hello"},
            format="test",
        )
        written = result.write_to(tmp_path)
        assert len(written) == 1
        assert (tmp_path / "subdir" / "output.txt").read_text() == "hello"


# ---------------------------------------------------------------------------
# ManifestExporter
# ---------------------------------------------------------------------------

class TestManifestExporter:
    def test_basic_export(self, all_metrics, sources, exposures):
        from kelpmesh.semantic.exporters.manifest import ManifestExporter
        exp = ManifestExporter(all_metrics, sources, exposures, "test_project")
        result = exp.export()
        assert "semantic_manifest.json" in result.files
        manifest = json.loads(result.files["semantic_manifest.json"])
        assert manifest["project"] == "test_project"
        assert len(manifest["metrics"]) == len(all_metrics)
        assert len(manifest["sources"]) == len(sources)
        assert len(manifest["exposures"]) == len(exposures)

    def test_ratio_metric_in_manifest(self, ratio_metric):
        from kelpmesh.semantic.exporters.manifest import ManifestExporter
        exp = ManifestExporter([ratio_metric])
        result = exp.export()
        manifest = json.loads(result.files["semantic_manifest.json"])
        m = manifest["metrics"][0]
        assert m["type"] == "ratio"
        assert m["numerator"] == "converted"
        assert m["denominator"] == "total_sessions"

    def test_derived_metric_in_manifest(self, derived_metric):
        from kelpmesh.semantic.exporters.manifest import ManifestExporter
        exp = ManifestExporter([derived_metric])
        result = exp.export()
        manifest = json.loads(result.files["semantic_manifest.json"])
        m = manifest["metrics"][0]
        assert m["type"] == "derived"
        assert "expression" in m

    def test_generated_sql_in_manifest(self, simple_metrics):
        from kelpmesh.semantic.exporters.manifest import ManifestExporter
        exp = ManifestExporter(simple_metrics)
        result = exp.export()
        manifest = json.loads(result.files["semantic_manifest.json"])
        count_m = next(m for m in manifest["metrics"] if m["name"] == "total_orders")
        assert "generated_sql" in count_m
        assert "COUNT(*)" in count_m["generated_sql"]


# ---------------------------------------------------------------------------
# LookerExporter
# ---------------------------------------------------------------------------

class TestLookerExporter:
    def test_produces_lkml_files(self, simple_metrics):
        from kelpmesh.semantic.exporters.looker import LookerExporter
        exp = LookerExporter(simple_metrics)
        result = exp.export()
        assert any(".view.lkml" in k for k in result.files)
        assert any(".explore.lkml" in k for k in result.files)

    def test_view_contains_measures(self, simple_metrics):
        from kelpmesh.semantic.exporters.looker import LookerExporter
        exp = LookerExporter(simple_metrics)
        result = exp.export()
        view_content = next(v for k, v in result.files.items() if ".view.lkml" in k)
        assert "measure: total_orders" in view_content
        assert "measure: total_revenue" in view_content
        assert "type: count" in view_content
        assert "type: sum" in view_content

    def test_view_contains_dimensions(self, simple_metrics):
        from kelpmesh.semantic.exporters.looker import LookerExporter
        exp = LookerExporter(simple_metrics)
        result = exp.export()
        view_content = next(v for k, v in result.files.items() if ".view.lkml" in k)
        assert "dimension: status" in view_content

    def test_ratio_measure(self, ratio_metric):
        from kelpmesh.semantic.exporters.looker import LookerExporter
        exp = LookerExporter([ratio_metric])
        result = exp.export()
        view = next(v for k, v in result.files.items() if ".view.lkml" in k)
        assert "conversion_rate" in view
        assert "NULLIF" in view

    def test_format_string(self, simple_metrics):
        from kelpmesh.semantic.exporters.looker import LookerExporter
        exp = LookerExporter(simple_metrics)
        result = exp.export()
        view = next(v for k, v in result.files.items() if ".view.lkml" in k)
        assert "value_format" in view

    def test_tags_in_view(self, simple_metrics):
        from kelpmesh.semantic.exporters.looker import LookerExporter
        exp = LookerExporter(simple_metrics)
        result = exp.export()
        view = next(v for k, v in result.files.items() if ".view.lkml" in k)
        assert "finance" in view

    def test_explore_block(self, simple_metrics):
        from kelpmesh.semantic.exporters.looker import LookerExporter
        exp = LookerExporter(simple_metrics)
        result = exp.export()
        explore = next(v for k, v in result.files.items() if ".explore.lkml" in k)
        assert "explore:" in explore

    def test_one_file_pair_per_model(self, all_metrics):
        from kelpmesh.semantic.exporters.looker import LookerExporter
        exp = LookerExporter(all_metrics)
        result = exp.export()
        views = [k for k in result.files if ".view.lkml" in k]
        explores = [k for k in result.files if ".explore.lkml" in k]
        assert len(views) == len(explores)


# ---------------------------------------------------------------------------
# TableauExporter
# ---------------------------------------------------------------------------

class TestTableauExporter:
    def test_produces_tds_files(self, simple_metrics):
        from kelpmesh.semantic.exporters.tableau import TableauExporter
        exp = TableauExporter(simple_metrics)
        result = exp.export()
        assert any(".tds" in k for k in result.files)

    def test_tds_is_valid_xml(self, simple_metrics):
        import xml.etree.ElementTree as ET
        from kelpmesh.semantic.exporters.tableau import TableauExporter
        exp = TableauExporter(simple_metrics)
        result = exp.export()
        tds = next(v for k, v in result.files.items() if ".tds" in k)
        root = ET.fromstring(tds)
        assert root.tag == "datasource"

    def test_tds_contains_measures(self, simple_metrics):
        from kelpmesh.semantic.exporters.tableau import TableauExporter
        exp = TableauExporter(simple_metrics)
        result = exp.export()
        tds = next(v for k, v in result.files.items() if ".tds" in k)
        assert "total_orders" in tds
        assert "total_revenue" in tds

    def test_tds_dimensions(self, simple_metrics):
        from kelpmesh.semantic.exporters.tableau import TableauExporter
        exp = TableauExporter(simple_metrics)
        result = exp.export()
        tds = next(v for k, v in result.files.items() if ".tds" in k)
        assert "[status]" in tds

    def test_ratio_calculation(self, ratio_metric):
        from kelpmesh.semantic.exporters.tableau import TableauExporter
        exp = TableauExporter([ratio_metric])
        result = exp.export()
        tds = next(v for k, v in result.files.items() if ".tds" in k)
        assert "NULLIF" in tds

    def test_format_string(self, simple_metrics):
        from kelpmesh.semantic.exporters.tableau import TableauExporter
        exp = TableauExporter(simple_metrics)
        result = exp.export()
        tds = next(v for k, v in result.files.items() if ".tds" in k)
        assert "$#,##0.00" in tds


# ---------------------------------------------------------------------------
# PowerBIExporter
# ---------------------------------------------------------------------------

class TestPowerBIExporter:
    def test_produces_bim_and_dax(self, simple_metrics):
        from kelpmesh.semantic.exporters.powerbi import PowerBIExporter
        exp = PowerBIExporter(simple_metrics, project_name="my_project")
        result = exp.export()
        assert any(".bim" in k for k in result.files)
        assert "measures.dax" in result.files

    def test_bim_is_valid_json(self, simple_metrics):
        from kelpmesh.semantic.exporters.powerbi import PowerBIExporter
        exp = PowerBIExporter(simple_metrics, project_name="my_project")
        result = exp.export()
        bim_content = next(v for k, v in result.files.items() if ".bim" in k)
        bim = json.loads(bim_content)
        assert "model" in bim
        assert "tables" in bim["model"]

    def test_bim_has_measures(self, simple_metrics):
        from kelpmesh.semantic.exporters.powerbi import PowerBIExporter
        exp = PowerBIExporter(simple_metrics, project_name="proj")
        result = exp.export()
        bim = json.loads(next(v for k, v in result.files.items() if ".bim" in k))
        all_measure_names = [
            m["name"]
            for t in bim["model"]["tables"]
            for m in t.get("measures", [])
        ]
        assert "Total Orders" in all_measure_names
        assert "Total Revenue" in all_measure_names

    def test_bim_has_columns(self, simple_metrics):
        from kelpmesh.semantic.exporters.powerbi import PowerBIExporter
        exp = PowerBIExporter(simple_metrics, project_name="proj")
        result = exp.export()
        bim = json.loads(next(v for k, v in result.files.items() if ".bim" in k))
        col_names = [
            c["name"]
            for t in bim["model"]["tables"]
            for c in t.get("columns", [])
        ]
        assert "status" in col_names

    def test_ratio_dax(self, ratio_metric):
        from kelpmesh.semantic.exporters.powerbi import PowerBIExporter
        exp = PowerBIExporter([ratio_metric], project_name="proj")
        result = exp.export()
        dax = result.files["measures.dax"]
        assert "DIVIDE" in dax

    def test_format_string_in_measure(self, simple_metrics):
        from kelpmesh.semantic.exporters.powerbi import PowerBIExporter
        exp = PowerBIExporter(simple_metrics, project_name="proj")
        result = exp.export()
        bim = json.loads(next(v for k, v in result.files.items() if ".bim" in k))
        measures = [
            m for t in bim["model"]["tables"]
            for m in t.get("measures", [])
            if m["name"] == "Total Revenue"
        ]
        assert measures[0].get("formatString") == "$#,##0.00"

    def test_dax_file_contains_measures(self, simple_metrics):
        from kelpmesh.semantic.exporters.powerbi import PowerBIExporter
        exp = PowerBIExporter(simple_metrics, project_name="proj")
        result = exp.export()
        dax = result.files["measures.dax"]
        assert "Total Orders" in dax
        assert "COUNTROWS" in dax


# ---------------------------------------------------------------------------
# QlikExporter
# ---------------------------------------------------------------------------

class TestQlikExporter:
    def test_produces_master_items_and_qvs(self, simple_metrics):
        from kelpmesh.semantic.exporters.qlik import QlikExporter
        exp = QlikExporter(simple_metrics)
        result = exp.export()
        assert "master_items.json" in result.files
        assert "load_script.qvs" in result.files

    def test_master_items_structure(self, simple_metrics):
        from kelpmesh.semantic.exporters.qlik import QlikExporter
        exp = QlikExporter(simple_metrics)
        result = exp.export()
        mi = json.loads(result.files["master_items.json"])
        assert "measures" in mi
        assert "dimensions" in mi
        assert len(mi["measures"]) == len(simple_metrics)

    def test_measure_labels(self, simple_metrics):
        from kelpmesh.semantic.exporters.qlik import QlikExporter
        exp = QlikExporter(simple_metrics)
        result = exp.export()
        mi = json.loads(result.files["master_items.json"])
        labels = [m["qMeasure"]["qLabel"] for m in mi["measures"]]
        assert "Total Orders" in labels
        assert "Total Revenue" in labels

    def test_dimension_items(self, simple_metrics):
        from kelpmesh.semantic.exporters.qlik import QlikExporter
        exp = QlikExporter(simple_metrics)
        result = exp.export()
        mi = json.loads(result.files["master_items.json"])
        dim_titles = [d["qMetaDef"]["title"] for d in mi["dimensions"]]
        assert "Status" in dim_titles

    def test_ratio_expression(self, ratio_metric):
        from kelpmesh.semantic.exporters.qlik import QlikExporter
        exp = QlikExporter([ratio_metric])
        result = exp.export()
        mi = json.loads(result.files["master_items.json"])
        expr = mi["measures"][0]["qMeasure"]["qDef"]
        assert "Sum([converted])" in expr
        assert "Sum([total_sessions])" in expr

    def test_format_string_in_measure(self, ratio_metric):
        from kelpmesh.semantic.exporters.qlik import QlikExporter
        exp = QlikExporter([ratio_metric])
        result = exp.export()
        mi = json.loads(result.files["master_items.json"])
        m = mi["measures"][0]
        assert "qNumFormat" in m["qMeasure"]

    def test_qvs_load_block(self, simple_metrics):
        from kelpmesh.semantic.exporters.qlik import QlikExporter
        exp = QlikExporter(simple_metrics)
        result = exp.export()
        qvs = result.files["load_script.qvs"]
        assert "LOAD" in qvs
        assert "fct_orders" in qvs
        assert ".qvd" in qvs


# ---------------------------------------------------------------------------
# EXPORTERS registry
# ---------------------------------------------------------------------------

class TestExporterRegistry:
    def test_all_formats_registered(self):
        from kelpmesh.semantic.exporters import EXPORTERS
        for fmt in ("manifest", "looker", "tableau", "powerbi", "qlik"):
            assert fmt in EXPORTERS

    def test_all_exporters_instantiate(self, simple_metrics):
        from kelpmesh.semantic.exporters import EXPORTERS
        for fmt, cls in EXPORTERS.items():
            exp = cls(simple_metrics, project_name="test")
            result = exp.export()
            assert result.files, f"Exporter '{fmt}' produced no files"

    def test_all_exporters_write_to_disk(self, tmp_path, simple_metrics):
        from kelpmesh.semantic.exporters import EXPORTERS
        for fmt, cls in EXPORTERS.items():
            exp = cls(simple_metrics, project_name="test")
            result = exp.export()
            written = result.write_to(tmp_path / fmt)
            assert written


# ---------------------------------------------------------------------------
# Serve app
# ---------------------------------------------------------------------------

class TestServeApp:
    @pytest.fixture
    def app_client(self, tmp_path):
        (tmp_path / "metrics.yml").write_text("""
metrics:
  - name: total_orders
    label: Total Orders
    model: fct_orders
    type: count
    dimensions: [status]
  - name: conversion_rate
    label: Conversion Rate
    model: fct_events
    type: ratio
    numerator: converted
    denominator: total_sessions
""", encoding="utf-8")
        from fastapi.testclient import TestClient
        from kelpmesh.semantic.serve import create_serve_app
        app = create_serve_app(tmp_path)
        return TestClient(app)

    def test_health(self, app_client):
        resp = app_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["metrics"] == 2

    def test_list_metrics(self, app_client):
        resp = app_client.get("/metrics")
        assert resp.status_code == 200
        metrics = resp.json()
        assert len(metrics) == 2
        names = [m["name"] for m in metrics]
        assert "total_orders" in names
        assert "conversion_rate" in names

    def test_get_metric(self, app_client):
        resp = app_client.get("/metrics/total_orders")
        assert resp.status_code == 200
        assert resp.json()["name"] == "total_orders"

    def test_get_metric_not_found(self, app_client):
        resp = app_client.get("/metrics/nonexistent")
        assert resp.status_code == 404

    def test_metric_sql(self, app_client):
        resp = app_client.get("/metrics/total_orders/sql")
        assert resp.status_code == 200
        data = resp.json()
        assert "COUNT(*)" in data["sql"]

    def test_metric_sql_with_group_by(self, app_client):
        resp = app_client.get("/metrics/total_orders/sql?group_by=status")
        assert resp.status_code == 200
        assert "GROUP BY" in resp.json()["sql"]

    def test_metric_sql_ratio_unsupported(self, app_client):
        resp = app_client.get("/metrics/conversion_rate/sql")
        assert resp.status_code == 400

    def test_export_manifest(self, app_client):
        resp = app_client.get("/export/manifest")
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        assert "semantic_manifest.json" in data["files"]

    def test_export_looker(self, app_client):
        resp = app_client.get("/export/looker")
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert any(".view.lkml" in k for k in files)

    def test_export_tableau(self, app_client):
        resp = app_client.get("/export/tableau")
        assert resp.status_code == 200
        assert any(".tds" in k for k in resp.json()["files"])

    def test_export_powerbi(self, app_client):
        resp = app_client.get("/export/powerbi")
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert any(".bim" in k for k in files)

    def test_export_qlik(self, app_client):
        resp = app_client.get("/export/qlik")
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert "master_items.json" in files

    def test_export_unknown_format(self, app_client):
        resp = app_client.get("/export/unknownformat")
        assert resp.status_code == 400

    def test_list_sources_empty(self, app_client):
        resp = app_client.get("/sources")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_exposures_empty(self, app_client):
        resp = app_client.get("/exposures")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
