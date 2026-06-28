import json
import logging
from kelpmesh.core.project import Project
from kelpmesh.state.engine import StateEngine

_logger = logging.getLogger(__name__)


class SchemaDriftDetector:
    def __init__(self, project: Project, state: StateEngine):
        self.project = project
        self.state = state

    def check_model(self, model_name: str, adapter) -> dict | None:
        model = self.project.get_model(model_name)
        if not model:
            return None

        table_name = model.alias or model_name
        if not adapter.table_exists(table_name):
            return None

        try:
            current_schema = adapter.table_schema(table_name)
        except Exception as e:
            _logger.debug("Schema drift check failed for %s: %s", table_name, e)
            return None

        current_json = json.dumps(current_schema, default=str)
        stored = self.state.get_schema(table_name)

        if stored is None:
            self.state.record_schema(table_name, current_json)
            return {
                "model": model_name,
                "table": table_name,
                "status": "first_checked",
                "changes": [],
                "current_columns": len(current_schema),
            }

        try:
            previous_schema = json.loads(stored["schema_json"])
        except (json.JSONDecodeError, TypeError):
            previous_schema = []

        current_cols = {c["column_name"]: c for c in current_schema}
        previous_cols = {c["column_name"]: c for c in previous_schema}

        changes = []
        for name, col in current_cols.items():
            if name not in previous_cols:
                changes.append({
                    "type": "added",
                    "column": name,
                    "data_type": col.get("data_type", "unknown"),
                })
            elif col.get("data_type") != previous_cols[name].get("data_type"):
                changes.append({
                    "type": "changed",
                    "column": name,
                    "from_type": previous_cols[name].get("data_type", "unknown"),
                    "to_type": col.get("data_type", "unknown"),
                })

        for name in previous_cols:
            if name not in current_cols:
                changes.append({
                    "type": "removed",
                    "column": name,
                })

        if changes:
            self.state.record_schema(table_name, current_json)
            return {
                "model": model_name,
                "table": table_name,
                "status": "drift_detected",
                "changes": changes,
                "current_columns": len(current_schema),
                "previous_columns": len(previous_schema),
            }

        return {
            "model": model_name,
            "table": table_name,
            "status": "unchanged",
            "changes": [],
            "current_columns": len(current_schema),
        }

    def check_all(self, adapter) -> list[dict]:
        results = []
        for name in self.project.models:
            result = self.check_model(name, adapter)
            if result:
                results.append(result)
        return results
