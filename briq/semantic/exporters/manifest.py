"""Universal semantic manifest exporter — target/semantic_manifest.json."""

from __future__ import annotations
import json
from briq.semantic.exporters.base import BaseExporter, ExportResult


class ManifestExporter(BaseExporter):
    """Writes a machine-readable JSON manifest of the full semantic layer."""

    format = "manifest"

    def export(self) -> ExportResult:
        manifest = {
            "briq_version": "1.0",
            "project": self.project_name,
            "metrics": [self._metric_dict(m) for m in self.metrics],
            "sources": [self._source_dict(s) for s in self.sources],
            "exposures": [self._exposure_dict(e) for e in self.exposures],
        }
        return ExportResult(
            files={"semantic_manifest.json": json.dumps(manifest, indent=2)},
            format=self.format,
        )

    def _metric_dict(self, m) -> dict:
        d: dict = {
            "name": m.name,
            "label": self._label(m),
            "type": m.type,
            "model": m.model,
            "description": self._description(m),
            "dimensions": m.dimensions,
            "timestamp": m.timestamp,
            "time_granularity": m.time_granularity,
            "tags": m.tags,
        }
        if m.sql:
            d["sql"] = m.sql
        if m.format_string:
            d["format_string"] = m.format_string
        if m.filters:
            d["filters"] = [{"field": f.field, "operator": f.operator, "value": f.value} for f in m.filters]
        if m.type == "ratio":
            d["numerator"] = m.numerator
            d["denominator"] = m.denominator
        elif m.type == "derived":
            d["expression"] = m.expression
        else:
            try:
                d["generated_sql"] = m.generate_sql()
            except Exception:
                pass
        return d

    def _source_dict(self, s) -> dict:
        return {
            "name": s.name,
            "table": s.table,
            "description": s.description,
            "loader": s.loader,
            "freshness_status": s.freshness_status,
        }

    def _exposure_dict(self, e) -> dict:
        return {
            "name": e.name,
            "type": e.type,
            "owner": e.owner,
            "url": e.url,
            "depends_on": e.depends_on,
            "description": e.description,
        }
