"""LookML exporter — generates view + explore .lkml files for Looker."""

from __future__ import annotations
from collections import defaultdict
from kelpmesh.semantic.exporters.base import BaseExporter, ExportResult


_LOOKER_TYPE = {
    "count": "count",
    "count_distinct": "count_distinct",
    "sum": "sum",
    "average": "average",
    "min": "min",
    "max": "max",
    "expression": "number",
    "ratio": "number",
    "derived": "number",
}


class LookerExporter(BaseExporter):
    """Generates one .lkml file per model containing view + explore blocks."""

    format = "looker"

    def export(self) -> ExportResult:
        by_model: dict[str, list] = defaultdict(list)
        for m in self.metrics:
            by_model[m.model or "briq_metrics"].append(m)

        files: dict[str, str] = {}
        for model_name, metrics in by_model.items():
            safe = self._safe_name(model_name)
            files[f"{safe}.view.lkml"] = self._view_block(model_name, metrics)
            files[f"{safe}.explore.lkml"] = self._explore_block(model_name, metrics)

        return ExportResult(files=files, format=self.format)

    # ---- view --------------------------------------------------------------

    def _view_block(self, model_name: str, metrics: list) -> str:
        dims = self._collect_dimensions(metrics)
        lines = [f"view: {self._safe_name(model_name)} {{", f"  sql_table_name: {model_name} ;;", ""]

        for dim in dims:
            lines += [
                f"  dimension: {self._safe_name(dim)} {{",
                f"    type: string",
                f"    sql: ${{TABLE}}.{dim} ;;",
                f"    label: \"{dim.replace('_', ' ').title()}\"",
                "  }",
                "",
            ]

        for m in metrics:
            lines += self._measure_block(m)

        lines.append("}")
        return "\n".join(lines)

    def _measure_block(self, m) -> list[str]:
        lk_type = _LOOKER_TYPE.get(m.type, "number")
        lines = [
            f"  measure: {self._safe_name(m.name)} {{",
            f"    type: {lk_type}",
            f"    label: \"{self._label(m)}\"",
            f"    description: \"{self._description(m)}\"",
        ]
        if m.type in ("sum", "average", "min", "max", "count_distinct") and m.sql:
            lines.append(f"    sql: ${{TABLE}}.{m.sql} ;;")
        elif m.type == "expression" and m.sql:
            lines.append(f"    sql: {m.sql} ;;")
        elif m.type == "ratio" and m.numerator and m.denominator:
            lines.append(f"    sql: ${{TABLE}}.{m.numerator} / NULLIF(${{TABLE}}.{m.denominator}, 0) ;;")
        elif m.type == "derived" and m.expression:
            expr = m.expression
            for other in [x.name for x in self._all_metrics_by_name()]:
                expr = expr.replace(f"{{{{{other}}}}}", f"${{{{measure: {self._safe_name(other)}}}}}")
            lines.append(f"    sql: {expr} ;;")

        if m.filters:
            for f in m.filters:
                lines.append(f"    filters: [{self._safe_name(f.field)}: \"{f.value}\"]")

        if m.format_string:
            lines.append(f"    value_format: \"{m.format_string}\"")

        if m.tags:
            tags_str = ", ".join(f'"{t}"' for t in m.tags)
            lines.append(f"    tags: [{tags_str}]")

        lines += ["  }", ""]
        return lines

    def _all_metrics_by_name(self) -> list:
        return self.metrics

    # ---- explore -----------------------------------------------------------

    def _explore_block(self, model_name: str, metrics: list) -> str:
        safe = self._safe_name(model_name)
        lines = [
            f"explore: {safe} {{",
            f"  label: \"{model_name.replace('_', ' ').title()}\"",
            f"  view_name: {safe}",
            "}",
        ]
        return "\n".join(lines)

    def _collect_dimensions(self, metrics: list) -> list[str]:
        seen: set[str] = set()
        dims: list[str] = []
        for m in metrics:
            for d in m.dimensions:
                if d not in seen:
                    seen.add(d)
                    dims.append(d)
        return dims
