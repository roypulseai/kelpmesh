"""Generate SQL assertions from schema.yml test declarations.

Supported test types (matching dbt's built-in generic tests):
  not_null, unique, accepted_values, relationships
"""

from pathlib import Path
from kelpmesh.core.schema_yaml import SchemaYaml
from kelpmesh.adapters.base import sanitize_name


def _not_null_sql(table: str, column: str) -> str:
    safe_t = sanitize_name(table)
    safe_c = sanitize_name(column)
    return f"SELECT COUNT(*) AS failures FROM {safe_t} WHERE {safe_c} IS NULL"


def _unique_sql(table: str, column: str) -> str:
    safe_t = sanitize_name(table)
    safe_c = sanitize_name(column)
    return (
        f"SELECT COUNT(*) AS failures FROM ("
        f"SELECT {safe_c} FROM {safe_t} WHERE {safe_c} IS NOT NULL "
        f"GROUP BY {safe_c} HAVING COUNT(*) > 1"
        f") _km_unique"
    )


def _accepted_values_sql(table: str, column: str, values: list) -> str:
    safe_t = sanitize_name(table)
    safe_c = sanitize_name(column)
    quoted = ", ".join(f"'{v}'" for v in values)
    return (
        f"SELECT COUNT(*) AS failures FROM {safe_t} "
        f"WHERE {safe_c} IS NOT NULL AND {safe_c} NOT IN ({quoted})"
    )


def _relationships_sql(table: str, column: str, to_table: str, to_field: str) -> str:
    safe_t = sanitize_name(table)
    safe_c = sanitize_name(column)
    safe_ref = sanitize_name(to_table)
    safe_rf = sanitize_name(to_field)
    return (
        f"SELECT COUNT(*) AS failures FROM {safe_t} "
        f"WHERE {safe_c} IS NOT NULL "
        f"AND {safe_c} NOT IN (SELECT {safe_rf} FROM {safe_ref})"
    )


_GENERATORS = {
    "not_null": lambda t, c, cfg: _not_null_sql(t, c),
    "unique": lambda t, c, cfg: _unique_sql(t, c),
    "accepted_values": lambda t, c, cfg: _accepted_values_sql(t, c, cfg.get("values", [])),
    "relationships": lambda t, c, cfg: _relationships_sql(
        t, c,
        cfg.get("to", cfg.get("model", "")),
        cfg.get("field", cfg.get("column", "id")),
    ),
}


class SchemaTestGenerator:
    """Generates in-memory SQL assertion tests from a project's schema.yml files."""

    def __init__(self, schema: SchemaYaml):
        self.schema = schema

    def tests_for_model(self, model_name: str) -> list[dict]:
        """Return list of ``{"name": str, "sql": str, "severity": str}`` for *model_name*."""
        results = []
        for t in self.schema.model_tests(model_name):
            test_type = t["type"]
            column = t["column"]
            config = t["config"]
            severity = config.pop("severity", "error") if isinstance(config, dict) else "error"
            gen = _GENERATORS.get(test_type)
            if gen is None or not column:
                continue
            try:
                sql = gen(model_name, column, config)
            except Exception:
                continue
            results.append({
                "name": f"{model_name}.{column}.{test_type}",
                "sql": sql,
                "severity": severity,
            })
        return results

    def all_tests(self, model_names: list[str] | None = None) -> list[dict]:
        names = model_names or self.schema.all_model_names()
        out = []
        for n in names:
            out.extend(self.tests_for_model(n))
        return out
