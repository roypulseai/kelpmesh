"""Lightweight FastAPI app exposing the semantic layer as a REST API."""

from __future__ import annotations
from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware
except ImportError as e:
    raise ImportError("fastapi is required for kelpmesh serve: pip install fastapi") from e

from kelpmesh.semantic import MetricLoader, SourceLoader, ExposureLoader, KelpMeshMetric
from kelpmesh.semantic.exporters import EXPORTERS


def create_serve_app(project_path: Path) -> FastAPI:
    metrics = MetricLoader.load(project_path)
    sources = SourceLoader.load(project_path)
    exposures = ExposureLoader.load(project_path)

    app = FastAPI(
        title="kelpmesh Semantic API",
        description="Query metrics and export semantic definitions.",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    metric_index: dict[str, KelpMeshMetric] = {m.name: m for m in metrics}

    @app.get("/metrics", summary="List all metrics")
    def list_metrics():
        return [
            {
                "name": m.name,
                "label": m.label,
                "type": m.type,
                "model": m.model,
                "description": m.description,
                "dimensions": m.dimensions,
                "tags": m.tags,
            }
            for m in metrics
        ]

    @app.get("/metrics/{name}", summary="Get a single metric definition")
    def get_metric(name: str):
        m = metric_index.get(name)
        if not m:
            raise HTTPException(status_code=404, detail=f"Metric '{name}' not found")
        return m.model_dump()

    @app.get("/metrics/{name}/sql", summary="Generate SQL for a metric")
    def metric_sql(
        name: str,
        group_by: Optional[str] = Query(None, description="Comma-separated dimension names"),
        where: Optional[str] = Query(None),
        limit: Optional[int] = Query(None),
    ):
        m = metric_index.get(name)
        if not m:
            raise HTTPException(status_code=404, detail=f"Metric '{name}' not found")
        if m.type in ("ratio", "derived"):
            raise HTTPException(
                status_code=400,
                detail=f"SQL generation not supported for '{m.type}' metrics via this endpoint",
            )
        gb = [d.strip() for d in group_by.split(",")] if group_by else None
        sql = m.generate_sql(group_by=gb, where=where, limit=limit)
        return {"metric": name, "sql": sql}

    @app.get("/sources", summary="List all sources")
    def list_sources():
        return [
            {
                "name": s.name,
                "table": s.table,
                "description": s.description,
                "freshness_status": s.freshness_status,
            }
            for s in sources
        ]

    @app.get("/exposures", summary="List all exposures")
    def list_exposures():
        return [
            {
                "name": e.name,
                "type": e.type,
                "owner": e.owner,
                "depends_on": e.depends_on,
                "description": e.description,
            }
            for e in exposures
        ]

    @app.get("/export/{format}", summary="Export semantic layer in BI format")
    def export_format(format: str):
        if format not in EXPORTERS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown format '{format}'. Available: {list(EXPORTERS.keys())}",
            )
        exporter_cls = EXPORTERS[format]
        exporter = exporter_cls(
            metrics=metrics,
            sources=sources,
            exposures=exposures,
            project_name=project_path.name,
        )
        result = exporter.export()
        return {"format": format, "files": result.files}

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "metrics": len(metrics),
            "sources": len(sources),
            "exposures": len(exposures),
        }

    return app
