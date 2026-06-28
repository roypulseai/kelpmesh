"""Compare kelpmesh model output against dbt output row-by-row."""
import logging
from kelpmesh.core.project import Project
from kelpmesh.adapters.base import WarehouseAdapter
from kelpmesh.state.engine import StateEngine

_logger = logging.getLogger(__name__)


class ComparisonEngine:
    def __init__(self, project: Project, briq_adapter: WarehouseAdapter, dbt_adapter: WarehouseAdapter | None = None):
        self.project = project
        self.briq_adapter = briq_adapter
        self.dbt_adapter = dbt_adapter

    def compare(self, model_name: str) -> dict:
        model = self.project.get_model(model_name)
        if not model:
            return {"error": f"Model '{model_name}' not found"}

        table_name = model.alias or model_name
        result = {
            "model": model_name,
            "table": table_name,
            "briq_row_count": 0,
            "dbt_row_count": 0,
            "match": False,
            "differences": [],
        }

        try:
            result["briq_row_count"] = self.briq_adapter.fetch_row_count(table_name)
        except Exception as e:
            result["briq_row_count"] = f"error: {e}"

        if self.dbt_adapter:
            try:
                result["dbt_row_count"] = self.dbt_adapter.fetch_row_count(table_name)
            except Exception as e:
                result["dbt_row_count"] = f"error: {e}"

        if isinstance(result["briq_row_count"], int) and isinstance(result["dbt_row_count"], int):
            result["match"] = result["briq_row_count"] == result["dbt_row_count"]
            if not result["match"]:
                result["differences"].append(
                    f"Row count mismatch: kelpmesh={result['briq_row_count']}, dbt={result['dbt_row_count']}"
                )
                try:
                    briq_data = self.briq_adapter.execute(f"SELECT * FROM {table_name} ORDER BY 1")
                    dbt_data = self.dbt_adapter.execute(f"SELECT * FROM {table_name} ORDER BY 1")
                    briq_set = {tuple(d.values()) for d in briq_data}
                    dbt_set = {tuple(d.values()) for d in dbt_data}
                    only_in_briq = len(briq_set - dbt_set)
                    only_in_dbt = len(dbt_set - briq_set)
                    if only_in_briq:
                        result["differences"].append(f"Rows only in kelpmesh: {only_in_briq}")
                    if only_in_dbt:
                        result["differences"].append(f"Rows only in dbt: {only_in_dbt}")
                except Exception as e:
                    _logger.debug("Row comparison failed for %s: %s", model_name, e)

        return result
