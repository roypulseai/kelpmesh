from pathlib import Path
from typing import Any
from kelpmesh.adapters.base import WarehouseAdapter


class TestRunner:
    def __init__(self, adapter: WarehouseAdapter, schema_tests: list[dict] | None = None):
        self.adapter = adapter
        self._schema_tests: list[dict] = schema_tests or []

    def _parse_severity(self, sql: str) -> str:
        for line in sql.splitlines():
            stripped = line.strip()
            if stripped.startswith("-- severity:"):
                return stripped.split(":")[1].strip().lower()
            if stripped.startswith("-- severity "):
                return stripped.split(" ")[-1].strip().lower()
        return "error"

    def run_test(self, test_sql: str, test_name: str) -> dict:
        severity = self._parse_severity(test_sql)
        try:
            result = self.adapter.execute(test_sql)
            if result and len(result) > 0:
                row = result[0]
                if "failures" in row:
                    failures = row["failures"]
                elif "num_failures" in row:
                    failures = row["num_failures"]
                elif "cnt" in row:
                    failures = row["cnt"]
                elif len(row) > 0:
                    failures = list(row.values())[0]
                else:
                    failures = 0
            else:
                failures = 0
            return {
                "name": test_name,
                "passed": failures == 0 or failures is None,
                "failures": int(failures) if failures is not None else 0,
                "error": None,
                "severity": severity,
            }
        except Exception as e:
            return {
                "name": test_name,
                "passed": False,
                "failures": 1,
                "error": str(e),
                "severity": severity,
            }

    def run_all(self, tests_path: Path) -> list[dict]:
        results = []
        if tests_path.exists():
            for test_file in sorted(tests_path.rglob("*.sql")):
                sql = test_file.read_text(encoding="utf-8")
                test_name = test_file.stem
                results.append(self.run_test(sql, test_name))
        # Generic tests from schema.yml
        for t in self._schema_tests:
            result = self.run_test(t["sql"], t["name"])
            result["severity"] = t.get("severity", "error")
            results.append(result)
        return results

    def run_for_model(self, tests_path: Path, model_name: str) -> list[dict]:
        results = []
        model_test_dir = tests_path / model_name
        if model_test_dir.exists():
            for test_file in sorted(model_test_dir.rglob("*.sql")):
                sql = test_file.read_text(encoding="utf-8")
                test_name = f"{model_name}/{test_file.stem}"
                result = self.run_test(sql, test_name)
                results.append(result)
        pattern_file = tests_path / f"{model_name}.sql"
        if pattern_file.exists():
            sql = pattern_file.read_text(encoding="utf-8")
            result = self.run_test(sql, model_name)
            results.append(result)
        return results
