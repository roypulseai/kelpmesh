"""Parse schema.yml / models.yml files for descriptions, column metadata, and test definitions."""

from pathlib import Path
from typing import Any
import yaml
import logging

_logger = logging.getLogger(__name__)

_SCHEMA_FILENAMES = {"schema.yml", "schema.yaml", "models.yml", "models.yaml"}


class SchemaYaml:
    """Loads and indexes all schema.yml / models.yml files under a project path."""

    def __init__(self, project_path: Path | None = None):
        self._models: dict[str, dict] = {}
        self._sources: dict[str, dict] = {}
        self._load(project_path or Path.cwd())

    def _load(self, project_path: Path):
        for f in sorted(project_path.rglob("*.yml")):
            if f.name not in _SCHEMA_FILENAMES:
                continue
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except Exception as e:
                _logger.debug("Could not parse %s: %s", f, e)
                continue

            for m in data.get("models", []):
                name = m.get("name")
                if name:
                    self._models[name] = m

            for s in data.get("sources", []):
                src_name = s.get("name", "")
                for tbl in s.get("tables", []):
                    key = f"{src_name}.{tbl.get('name', '')}"
                    self._sources[key] = tbl

    # ── Model metadata ────────────────────────────────────────────────────

    def model_description(self, name: str) -> str:
        return self._models.get(name, {}).get("description", "")

    def column_descriptions(self, name: str) -> dict[str, str]:
        cols = self._models.get(name, {}).get("columns", [])
        return {c["name"]: c.get("description", "") for c in cols if "name" in c}

    def column_metadata(self, name: str) -> list[dict]:
        """Return full column metadata list (name, description, tests, data_type, constraints)."""
        return self._models.get(name, {}).get("columns", [])

    def model_tags(self, name: str) -> list[str]:
        return self._models.get(name, {}).get("tags", [])

    def model_contract(self, name: str) -> dict:
        return self._models.get(name, {}).get("contract", {})

    # ── Test extraction ───────────────────────────────────────────────────

    def model_tests(self, name: str) -> list[dict]:
        """Return all column-level and model-level tests declared for *name*."""
        m = self._models.get(name, {})
        tests = []

        # Column-level tests
        for col in m.get("columns", []):
            col_name = col.get("name")
            if not col_name:
                continue
            for t in col.get("tests", []):
                tests.append(_normalise_test(t, col_name))

        # Model-level tests (rare but valid)
        for t in m.get("tests", []):
            tests.append(_normalise_test(t, None))

        return tests

    def all_model_names(self) -> list[str]:
        return list(self._models.keys())


def _normalise_test(t: Any, column: str | None) -> dict:
    """Normalise a test entry to ``{"type": str, "column": str|None, "config": dict}``."""
    if isinstance(t, str):
        return {"type": t, "column": column, "config": {}}
    if isinstance(t, dict):
        type_key = next(iter(t), None)
        config = t.get(type_key, {}) if type_key else {}
        if not isinstance(config, dict):
            config = {"values": config}
        return {"type": type_key, "column": column, "config": config}
    return {"type": str(t), "column": column, "config": {}}
