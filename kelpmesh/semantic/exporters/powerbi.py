"""Power BI exporter — BIM JSON (Tabular Model) + DAX measures file."""

from __future__ import annotations
import json
from collections import defaultdict
from kelpmesh.semantic.exporters.base import BaseExporter, ExportResult


_DAX_AGG = {
    "count": "COUNTROWS",
    "count_distinct": "DISTINCTCOUNT",
    "sum": "SUM",
    "average": "AVERAGE",
    "min": "MIN",
    "max": "MAX",
}


class PowerBIExporter(BaseExporter):
    """Generates a .bim Tabular Model JSON and a measures.dax companion file."""

    format = "powerbi"

    def export(self) -> ExportResult:
        by_model: dict[str, list] = defaultdict(list)
        for m in self.metrics:
            by_model[m.model or "kelpmesh_metrics"].append(m)

        tables = []
        dax_lines: list[str] = [f"-- DAX Measures for {self.project_name}", ""]

        for model_name, metrics in by_model.items():
            table = self._build_table(model_name, metrics)
            tables.append(table)
            dax_lines.append(f"-- Table: {model_name}")
            for m in metrics:
                dax_lines.append(f"[{self._label(m)}] = {self._dax_expression(m, model_name)}")
            dax_lines.append("")

        bim = {
            "name": self.project_name,
            "compatibilityLevel": 1550,
            "model": {
                "culture": "en-US",
                "tables": tables,
                "relationships": [],
                "annotations": [
                    {"name": "kelpmesh_version", "value": "1.0"},
                    {"name": "exporter", "value": "kelpmesh semantic layer"},
                ],
            },
        }

        return ExportResult(
            files={
                f"{self._safe_name(self.project_name)}.bim": json.dumps(bim, indent=2),
                "measures.dax": "\n".join(dax_lines),
            },
            format=self.format,
        )

    def _build_table(self, model_name: str, metrics: list) -> dict:
        dims = self._collect_dimensions(metrics)
        columns = []

        for dim in dims:
            columns.append({
                "name": dim,
                "dataType": "string",
                "sourceColumn": dim,
                "summarizeBy": "none",
                "annotations": [{"name": "SummarizationSetBy", "value": "Automatic"}],
            })

        measures = []
        for m in metrics:
            measure: dict = {
                "name": self._label(m),
                "expression": self._dax_expression(m, model_name),
                "description": self._description(m),
            }
            if m.format_string:
                measure["formatString"] = m.format_string
            if m.tags:
                measure["annotations"] = [{"name": "tags", "value": ", ".join(m.tags)}]
            measures.append(measure)

        return {
            "name": model_name,
            "columns": columns,
            "measures": measures,
            "partitions": [
                {
                    "name": f"{model_name}-partition",
                    "mode": "import",
                    "source": {
                        "type": "m",
                        "expression": [
                            f'let',
                            f'    Source = Sql.Database("{{server}}", "{{database}}"),',
                            f'    {model_name} = Source{{[Schema="dbo", Item="{model_name}"]}}[Data]',
                            f'in',
                            f'    {model_name}',
                        ],
                    },
                }
            ],
        }

    def _dax_expression(self, m, model_name: str) -> str:
        tbl = f"'{model_name}'"
        if m.type == "count":
            return f"COUNTROWS({tbl})"
        elif m.type == "count_distinct" and m.sql:
            return f"DISTINCTCOUNT({tbl}[{m.sql}])"
        elif m.type in ("sum", "average", "min", "max") and m.sql:
            fn = _DAX_AGG[m.type]
            return f"{fn}({tbl}[{m.sql}])"
        elif m.type == "expression" and m.sql:
            return m.sql
        elif m.type == "ratio" and m.numerator and m.denominator:
            return (
                f"DIVIDE("
                f"[{self._label_for(m.numerator)}], "
                f"[{self._label_for(m.denominator)}], 0)"
            )
        elif m.type == "derived" and m.expression:
            expr = m.expression
            for other in self.metrics:
                expr = expr.replace(f"{{{{{other.name}}}}}", f"[{self._label(other)}]")
            return expr
        return f"COUNTROWS({tbl})"

    def _label_for(self, name: str) -> str:
        for m in self.metrics:
            if m.name == name:
                return self._label(m)
        return name.replace("_", " ").title()

    def _collect_dimensions(self, metrics: list) -> list[str]:
        seen: set[str] = set()
        dims: list[str] = []
        for m in metrics:
            for d in m.dimensions:
                if d not in seen:
                    seen.add(d)
                    dims.append(d)
        return dims
