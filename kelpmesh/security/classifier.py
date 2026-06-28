"""Data Classification — tag columns as pii/sensitive/restricted/internal."""

from pathlib import Path
from typing import Literal

import yaml

SensitivityLevel = Literal["pii", "sensitive", "restricted", "internal"]

DEFAULT_RULES = {
    "email": "pii",
    "phone": "pii",
    "mobile": "pii",
    "ssn": "pii",
    "passport": "pii",
    "tax_id": "pii",
    "national_id": "pii",
    "credit_card": "sensitive",
    "cvv": "sensitive",
    "password": "restricted",
    "password_hash": "sensitive",
    "secret": "restricted",
    "token": "sensitive",
    "api_key": "sensitive",
    "salary": "sensitive",
    "bonus": "sensitive",
    "health": "sensitive",
    "diagnosis": "sensitive",
    "address": "pii",
    "birth_date": "pii",
    "first_name": "pii",
    "last_name": "pii",
    "full_name": "pii",
}


class DataClassifier:
    """Load and query data classification rules from classify.yml + built-in defaults."""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self._rules: dict[str, dict[str, SensitivityLevel]] = {}
        self._load()

    def _load(self):
        config_path = self.project_path / "classify.yml"
        self._rules = {}
        if config_path.exists():
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            for table, cols in raw.items():
                if isinstance(cols, dict):
                    self._rules[table.lower()] = {
                        col.lower(): sens for col, sens in cols.items()
                    }

    def classify(self, table: str, column: str) -> SensitivityLevel:
        table_lower = table.lower()
        col_lower = column.lower()
        if table_lower in self._rules and col_lower in self._rules[table_lower]:
            return self._rules[table_lower][col_lower]
        return DEFAULT_RULES.get(col_lower, "internal")

    def classify_columns(
        self, table: str, columns: list[str]
    ) -> list[tuple[str, SensitivityLevel]]:
        return [(c, self.classify(table, c)) for c in columns]

    def columns_by_sensitivity(
        self, table: str, level: SensitivityLevel
    ) -> list[str]:
        table_lower = table.lower()
        result: list[str] = []
        for col_name, sens in DEFAULT_RULES.items():
            if sens == level:
                result.append(col_name)
        if table_lower in self._rules:
            for col_name, sens in self._rules[table_lower].items():
                if col_name not in result and sens == level:
                    result.append(col_name)
        return sorted(set(result))

    def get_table_rules(self, table: str) -> dict[str, SensitivityLevel]:
        table_lower = table.lower()
        return dict(self._rules.get(table_lower, {}))

    def all_classified_tables(self) -> list[str]:
        return sorted(self._rules.keys())

    def is_classified(self, table: str, column: str) -> bool:
        return self.classify(table, column) != "internal"

    @staticmethod
    def generate_stub(path: Path) -> None:
        stub = """# classify.yml — Data classification rules
# Levels: pii, sensitive, restricted, internal
#
# Unmatched columns default to "internal".
# Built-in name-based rules cover: email, phone, ssn, credit_card, password, etc.
#
# To override or add rules per table:
#
# users:
#   email: pii
#   phone: pii
#   role: internal
#
# orders:
#   credit_card: sensitive
#   amount: internal
"""
        path.write_text(stub, encoding="utf-8")
