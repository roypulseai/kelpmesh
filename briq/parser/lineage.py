import logging
from briq.core.project import Project
from briq.parser.sql import SQLParser
import sqlglot
from sqlglot import exp

_logger = logging.getLogger(__name__)


class LineageExplorer:
    def __init__(self, project: Project):
        self.project = project
        self.parser = SQLParser()

    def column_lineage(self, model_name: str, column: str) -> list[dict]:
        model = self.project.get_model(model_name)
        if not model:
            return []
        lineage = []
        try:
            parsed = sqlglot.parse(model.sql)
            if not parsed or not parsed[0]:
                return lineage
            for select in parsed[0].find_all(exp.Select):
                for e in select.expressions:
                    alias = e.alias or e.output_name
                    if alias == column:
                        lineage.append({
                            "column": column,
                            "expression": str(e),
                            "model": model_name,
                            "sources": self._find_source_columns(e),
                        })
        except Exception as e:
            _logger.debug("Column lineage parse error for %s: %s", model_name, e)
        return lineage

    def _find_source_columns(self, node) -> list[dict]:
        sources = []
        for col in node.find_all(exp.Column):
            table = col.table
            sources.append({
                "column": col.name,
                "table": table or "unknown",
            })
        return sources

    def full_lineage(self, model_name: str) -> dict:
        model = self.project.get_model(model_name)
        if not model:
            return {}
        columns = self.parser.extract_columns(model.sql)
        return {
            "model": model_name,
            "upstream": list(self.project.get_upstream(model_name)),
            "downstream": list(self.project.get_downstream(model_name)),
            "columns": columns,
        }
