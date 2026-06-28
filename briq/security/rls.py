"""Row-Level Security (RLS) — policy-based row filters per role injected at query time."""

from pathlib import Path
from typing import Literal

import yaml


class RlsPolicy:
    """A single RLS policy: table, role, filter SQL."""

    def __init__(self, table: str, role: str, filter_sql: str) -> None:
        self.table = table.lower()
        self.role = role
        self.filter_sql = filter_sql


class RlsEngine:
    """Load and evaluate RLS policies from security.yml."""

    def __init__(self, project_path: Path) -> None:
        self._policies: list[RlsPolicy] = []
        self._load(project_path)

    def _load(self, project_path: Path):
        config_path = project_path / "security.yml"
        if not config_path.exists():
            config_path = project_path / "briq.yml"
            if config_path.exists():
                raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                rls_cfg = raw.get("rls", raw.get("security", {}).get("rls", {}))
            else:
                rls_cfg = {}
        else:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            rls_cfg = raw.get("rls", {})

        for table, policies in rls_cfg.items():
            if isinstance(policies, dict):
                for role, filter_sql in policies.items():
                    self._policies.append(RlsPolicy(table, role, str(filter_sql)))
            elif isinstance(policies, list):
                for entry in policies:
                    self._policies.append(
                        RlsPolicy(
                            table,
                            entry.get("role", "viewer"),
                            entry.get("filter", "1=1"),
                        )
                    )

    def get_filter(self, table: str, role: str) -> str | None:
        table_lower = table.lower()
        for p in self._policies:
            if p.table == table_lower and p.role == role:
                return p.filter_sql
        return None

    def apply_filter(self, sql: str, table: str, role: str) -> str:
        filter_sql = self.get_filter(table, role)
        if filter_sql is None:
            return sql
        return f"SELECT * FROM ({sql}) AS _rls WHERE {filter_sql}"

    def apply_filters_to_query(
        self, sql: str, tables: list[str], role: str
    ) -> str:
        for table in tables:
            sql = self.apply_filter(sql, table, role)
        return sql

    def list_policies(self) -> list[dict]:
        return [
            {"table": p.table, "role": p.role, "filter": p.filter_sql}
            for p in self._policies
        ]

    @staticmethod
    def generate_stub(path: Path) -> None:
        stub = """# security.yml — RLS and security policies
#
# RLS policies restrict which rows a role can see.
# Each policy is: <table>: <role>: <WHERE clause>
#
# rls:
#   orders:
#     viewer: "region = current_setting('app.region')"
#     editor: "1=1"
#   users:
#     viewer: "is_active = true"
#     admin: "1=1"
"""
        path.write_text(stub, encoding="utf-8")
