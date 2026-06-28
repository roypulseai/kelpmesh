"""Model access control — private | protected | public."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yaml

ACCESS_LEVELS = {"private": 0, "protected": 1, "public": 2}


@dataclass
class AccessPolicy:
    model: str
    access: str = "protected"  # private | protected | public
    group: str = "default"

    def is_public(self) -> bool:
        return self.access == "public"

    def is_protected(self) -> bool:
        return self.access == "protected"

    def is_private(self) -> bool:
        return self.access == "private"


class AccessChecker:
    """Load access policies from schema.yml and enforce cross-project rules.

    Rules:
    - ``public``    — any project in the mesh may reference this model
    - ``protected`` — only projects in the same group may reference it
    - ``private``   — no cross-project references allowed
    """

    def __init__(self, project_path: Path, project_group: str = "default"):
        self.project_path = project_path
        self.project_group = project_group
        self._policies: dict[str, AccessPolicy] = {}
        self._load()

    def get_policy(self, model_name: str, default_access: str = "protected") -> AccessPolicy:
        if model_name in self._policies:
            return self._policies[model_name]
        return AccessPolicy(model=model_name, access=default_access, group=self.project_group)

    def can_reference(
        self,
        model_name: str,
        referencing_group: str,
        default_access: str = "protected",
    ) -> tuple[bool, str]:
        """Return (allowed, reason)."""
        policy = self.get_policy(model_name, default_access)
        if policy.is_public():
            return True, "public"
        if policy.is_protected():
            if referencing_group == self.project_group:
                return True, "same group"
            return False, (
                f"Model '{model_name}' is protected (group: {self.project_group}); "
                f"referencing group '{referencing_group}' is different"
            )
        # private
        return False, f"Model '{model_name}' is private — no cross-project references allowed"

    def list_public_models(self) -> list[str]:
        return [m for m, p in self._policies.items() if p.is_public()]

    def list_protected_models(self) -> list[str]:
        return [m for m, p in self._policies.items() if p.is_protected()]

    def all_policies(self) -> list[AccessPolicy]:
        return list(self._policies.values())

    def _load(self) -> None:
        for fname in ("schema.yml", "schema.yaml", "models.yml", "models.yaml"):
            path = self.project_path / fname
            if not path.exists():
                # Also check models/ subdirectory
                path = self.project_path / "models" / fname
            if path.exists():
                self._parse_schema(path)
                return
        # Walk models/ for per-directory schema files
        models_dir = self.project_path / "models"
        if models_dir.exists():
            for schema_file in models_dir.rglob("schema.yml"):
                self._parse_schema(schema_file)
            for schema_file in models_dir.rglob("schema.yaml"):
                self._parse_schema(schema_file)

    def _parse_schema(self, path: Path) -> None:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return
        for m in raw.get("models", []):
            name = m.get("name", "")
            if not name:
                continue
            access = m.get("access", "protected")
            if access not in ACCESS_LEVELS:
                access = "protected"
            self._policies[name] = AccessPolicy(
                model=name,
                access=access,
                group=self.project_group,
            )
