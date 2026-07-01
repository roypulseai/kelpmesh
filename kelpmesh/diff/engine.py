import logging

from kelpmesh.adapters.base import WarehouseAdapter, sanitize_name
from kelpmesh.core.project import Project
from kelpmesh.state.engine import StateEngine

_logger = logging.getLogger(__name__)


class DiffEngine:
    def __init__(self, project: Project, adapter: WarehouseAdapter, state: StateEngine):
        self.project = project
        self.adapter = adapter
        self.state = state

    def compare(self, model_name: str) -> dict:
        model = self.project.get_model(model_name)
        if not model:
            return {"error": f"Model '{model_name}' not found"}

        table_name = model.alias or model_name
        if not self.adapter.table_exists(table_name):
            return {"error": f"Table or view '{table_name}' does not exist in warehouse"}

        current_rows = self.adapter.fetch_row_count(table_name)
        prev_state = self.state.get_state(model_name)
        prev_rows = prev_state["row_count"] if prev_state else 0

        result = {
            "model": model_name,
            "table": table_name,
            "current_row_count": current_rows,
            "previous_row_count": prev_rows,
            "row_count_delta": current_rows - prev_rows,
            "has_changed": current_rows != prev_rows,
        }

        if current_rows > 0 and prev_rows > 0 and current_rows != prev_rows:
            try:
                sample = self.adapter.preview(
                    f"SELECT * FROM {sanitize_name(table_name)}",
                    limit=5,
                )
                result["sample_diffs"] = sample
            except Exception as e:
                _logger.debug("Sample diff failed for %s: %s", model_name, e)
                result["sample_diffs"] = []

        return result

    def compare_all(self) -> list[dict]:
        results = []
        for name in self.project.models:
            result = self.compare(name)
            results.append(result)
        return results
