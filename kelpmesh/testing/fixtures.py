"""YAML fixture-based unit tests for KelpMesh models.

Fixture files live in tests/*.yaml and follow the SQLMesh-compatible format:

    test_stg_payments:
      model: my_project.stg_payments    # or just stg_payments
      inputs:
        seed_raw_payments:
          - id: 66
            order_id: 58
            payment_method: coupon
            amount: 1800
      outputs:
        query:
          - payment_id: 66
            order_id: 58
            amount: 18.0

Tests run entirely in-memory via DuckDB — no warehouse connection required.
Generate fixture files with: kelpmesh create_test <model>
"""

from __future__ import annotations

__all__ = ["FixtureTestRunner", "Fixture"]

import re
from pathlib import Path

import yaml


def _rows_match(expected: list[dict], actual: list[dict], tolerance: float = 1e-9) -> tuple[bool, str]:
    """Compare two row sets order-independently. Returns (passed, diff_message)."""
    if len(expected) != len(actual):
        return False, f"row count mismatch: expected {len(expected)}, got {len(actual)}"

    def _sort_key(row: dict):
        return tuple(str(v) for v in sorted(row.items()))

    exp_sorted = sorted(expected, key=_sort_key)
    act_sorted = sorted(actual, key=_sort_key)

    for i, (exp_row, act_row) in enumerate(zip(exp_sorted, act_sorted)):
        for col, exp_val in exp_row.items():
            act_val = act_row.get(col)
            if isinstance(exp_val, float) and isinstance(act_val, (int, float)):
                if abs(float(exp_val) - float(act_val)) > tolerance:
                    return False, f"row {i} col '{col}': expected {exp_val!r}, got {act_val!r}"
            elif exp_val != act_val:
                # Try numeric coercion
                try:
                    if abs(float(str(exp_val)) - float(str(act_val))) <= tolerance:
                        continue
                except (TypeError, ValueError):
                    pass
                return False, f"row {i} col '{col}': expected {exp_val!r}, got {act_val!r}"
    return True, ""


def _create_table_from_rows(conn, table_name: str, rows: list[dict]) -> None:
    """Create an in-memory DuckDB table from fixture row dicts."""
    if not rows:
        conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT 1 LIMIT 0")
        return

    cols = list(rows[0].keys())
    col_defs = []
    for col in cols:
        # Infer column type from first non-None value
        val = next((r[col] for r in rows if r.get(col) is not None), None)
        if isinstance(val, bool):
            col_type = "BOOLEAN"
        elif isinstance(val, int):
            col_type = "BIGINT"
        elif isinstance(val, float):
            col_type = "DOUBLE"
        else:
            col_type = "VARCHAR"
        col_defs.append(f'"{col}" {col_type}')

    conn.execute(f"CREATE OR REPLACE TABLE {table_name} ({', '.join(col_defs)})")
    for row in rows:
        values = []
        for col in cols:
            v = row.get(col)
            if v is None:
                values.append("NULL")
            elif isinstance(v, bool):
                values.append("TRUE" if v else "FALSE")
            elif isinstance(v, (int, float)):
                values.append(str(v))
            else:
                escaped = str(v).replace("'", "''")
                values.append(f"'{escaped}'")
        conn.execute(f"INSERT INTO {table_name} VALUES ({', '.join(values)})")


def _apply_input_substitutions(sql: str, input_tables: dict[str, str]) -> str:
    """Replace qualified table names (schema.table) with plain names in SQL."""
    for qualified, plain in sorted(input_tables.items(), key=lambda x: len(x[0]), reverse=True):
        parts = qualified.split(".")
        # Replace both qualified (schema.table) and unqualified (table) references
        if len(parts) > 1:
            sql = re.sub(
                r'(?<!["\w])' + re.escape(qualified) + r'(?!["\w])',
                plain,
                sql,
            )
    return sql


class FixtureTestRunner:
    """Runs YAML fixture tests in-memory using an embedded DuckDB."""

    def __init__(self, project=None):
        self.project = project

    def run_fixture_file(self, fixture_path: Path) -> list[dict]:
        """Run all tests in a fixture YAML file. Returns list of result dicts."""
        with open(fixture_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            return []

        results = []
        for test_name, test_def in data.items():
            if not isinstance(test_def, dict):
                continue
            result = self._run_single_fixture(test_name, test_def, fixture_path)
            results.append(result)
        return results

    def _run_single_fixture(self, test_name: str, test_def: dict, source_file: Path) -> dict:
        try:
            import duckdb
        except ImportError:
            return {
                "name": test_name,
                "passed": False,
                "failures": 1,
                "error": "duckdb not installed — run: pip install duckdb",
                "severity": "error",
                "type": "fixture",
            }

        model_ref = test_def.get("model", "")
        model_name = model_ref.split(".")[-1]
        inputs: dict[str, list[dict]] = test_def.get("inputs", {})
        outputs: dict = test_def.get("outputs", {})
        expected_rows: list[dict] = outputs.get("query", [])

        # Resolve model SQL from project
        model_sql = self._get_model_sql(model_name)
        if not model_sql:
            return {
                "name": test_name,
                "passed": False,
                "failures": 1,
                "error": f"Model '{model_name}' not found in project",
                "severity": "error",
                "type": "fixture",
            }

        try:
            conn = duckdb.connect(":memory:")

            # Build mapping of qualified → plain name for SQL rewriting
            input_name_map: dict[str, str] = {}
            for qualified_name, rows in inputs.items():
                plain = qualified_name.split(".")[-1]
                input_name_map[qualified_name] = plain
                _create_table_from_rows(conn, plain, rows)

            # Rewrite qualified refs in model SQL
            rewritten_sql = _apply_input_substitutions(model_sql, input_name_map)

            # Strip incremental predicates — fixtures always run in full mode
            rewritten_sql = re.sub(
                r"\{\{[\s%-]*if\s+is_incremental\(\)[\s%-]*\}\}.*?\{\{[\s%-]*endif[\s%-]*\}\}",
                "",
                rewritten_sql,
                flags=re.DOTALL | re.IGNORECASE,
            )
            rewritten_sql = re.sub(r"\bis_incremental\(\)", "FALSE", rewritten_sql)

            actual = conn.execute(rewritten_sql).fetchdf().to_dict(orient="records")
            conn.close()

            passed, diff_msg = _rows_match(expected_rows, actual)
            return {
                "name": test_name,
                "passed": passed,
                "failures": 0 if passed else 1,
                "error": diff_msg if not passed else None,
                "severity": "error",
                "type": "fixture",
            }

        except Exception as e:
            return {
                "name": test_name,
                "passed": False,
                "failures": 1,
                "error": str(e),
                "severity": "error",
                "type": "fixture",
            }

    def _get_model_sql(self, model_name: str) -> str | None:
        if self.project:
            model = self.project.get_model(model_name)
            if model and model.language == "sql":
                return model.sql
        return None

    def discover_fixtures(self, tests_path: Path) -> list[Path]:
        """Return all .yaml fixture files in the tests directory."""
        if not tests_path.exists():
            return []
        return sorted(tests_path.rglob("*.yaml")) + sorted(tests_path.rglob("*.yml"))

    def run_all_fixtures(self, tests_path: Path) -> list[dict]:
        """Run all fixture files in the tests directory."""
        results = []
        for fixture_file in self.discover_fixtures(tests_path):
            results.extend(self.run_fixture_file(fixture_file))
        return results

    def run_fixtures_for_model(self, tests_path: Path, model_name: str) -> list[dict]:
        """Run only fixtures that test a specific model."""
        all_results = []
        for fixture_file in self.discover_fixtures(tests_path):
            try:
                with open(fixture_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    continue
                for test_name, test_def in data.items():
                    if not isinstance(test_def, dict):
                        continue
                    if test_def.get("model", "").split(".")[-1] == model_name:
                        result = self._run_single_fixture(test_name, test_def, fixture_file)
                        all_results.append(result)
            except Exception:
                continue
        return all_results


Fixture = FixtureTestRunner
