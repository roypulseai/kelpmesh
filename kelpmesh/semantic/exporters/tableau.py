"""Tableau TDS (Tableau Data Source) exporter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict
from xml.dom import minidom

from kelpmesh.semantic.exporters.base import BaseExporter, ExportResult

_TABLEAU_AGG = {
    "count": "Count",
    "count_distinct": "CountD",
    "sum": "Sum",
    "average": "Avg",
    "min": "Min",
    "max": "Max",
}


class TableauExporter(BaseExporter):
    """Generates one .tds XML file per model for Tableau Desktop/Server."""

    format = "tableau"

    def export(self) -> ExportResult:
        by_model: dict[str, list] = defaultdict(list)
        for m in self.metrics:
            by_model[m.model or "kelpmesh_metrics"].append(m)

        files: dict[str, str] = {}
        for model_name, metrics in by_model.items():
            safe = self._safe_name(model_name)
            files[f"{safe}.tds"] = self._build_tds(model_name, metrics)

        return ExportResult(files=files, format=self.format)

    def _build_tds(self, model_name: str, metrics: list) -> str:
        root = ET.Element("datasource")
        root.set("name", model_name)
        root.set("inline", "true")
        root.set("source-platform", "win")
        root.set("version", "18.1")

        conn = ET.SubElement(root, "connection")
        conn.set("class", "genericodbc")
        conn.set("dbname", model_name)

        cols = ET.SubElement(root, "column-list")
        dims = self._collect_dimensions(metrics)

        for dim in dims:
            col = ET.SubElement(cols, "column")
            col.set("datatype", "string")
            col.set("name", f"[{dim}]")
            col.set("role", "dimension")
            col.set("type", "nominal")
            col.set("caption", dim.replace("_", " ").title())

        for m in metrics:
            col = ET.SubElement(cols, "column")
            col.set("datatype", "real")
            col.set("name", f"[{m.name}]")
            col.set("role", "measure")
            col.set("type", "quantitative")
            col.set("caption", self._label(m))
            if m.description:
                col.set("comment", m.description)

            agg = _TABLEAU_AGG.get(m.type)
            if agg:
                col.set("aggregation", agg)
            else:
                calc = ET.SubElement(col, "calculation")
                calc.set("class", "tableau")
                formula = self._calc_formula(m)
                calc.set("formula", formula)

            if m.format_string:
                col.set("default-format", m.format_string)

        return self._pretty(root)

    def _calc_formula(self, m) -> str:
        if m.type == "ratio" and m.numerator and m.denominator:
            return f"SUM([{m.numerator}]) / NULLIF(SUM([{m.denominator}]), 0)"
        elif m.type == "derived" and m.expression:
            expr = m.expression
            for name in [x.name for x in self.metrics]:
                expr = expr.replace(f"{{{{{name}}}}}", f"[{name}]")
            return expr
        elif m.type == "expression" and m.sql:
            return m.sql
        return f"COUNT([{m.name}])"

    def _collect_dimensions(self, metrics: list) -> list[str]:
        seen: set[str] = set()
        dims: list[str] = []
        for m in metrics:
            for d in m.dimensions:
                if d not in seen:
                    seen.add(d)
                    dims.append(d)
        return dims

    @staticmethod
    def _pretty(root: ET.Element) -> str:
        raw = ET.tostring(root, encoding="unicode")
        reparsed = minidom.parseString(raw)
        return reparsed.toprettyxml(indent="  ")
