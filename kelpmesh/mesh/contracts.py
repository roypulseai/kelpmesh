"""Producer/consumer contracts — versioned model interface declarations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class InterfaceColumn:
    name: str
    data_type: str = "unknown"
    description: str = ""
    required: bool = True


@dataclass
class InterfaceModel:
    name: str
    access: str = "public"
    version: int = 1
    columns: list[InterfaceColumn] = field(default_factory=list)
    description: str = ""

    def column_names(self) -> set[str]:
        return {c.name for c in self.columns}

    def required_columns(self) -> list[InterfaceColumn]:
        return [c for c in self.columns if c.required]


@dataclass
class ProducerContract:
    """Interface a project publishes for downstream consumers."""
    project: str
    version: int = 1
    published_at: str = ""
    models: list[InterfaceModel] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # I/O                                                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, project_path: Path) -> Optional["ProducerContract"]:
        for fname in ("interface.yml", "interface.yaml"):
            path = project_path / fname
            if path.exists():
                return cls._from_file(path)
        return None

    @classmethod
    def _from_file(cls, path: Path) -> "ProducerContract":
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data = raw.get("interface", raw)
        models = []
        for m in data.get("models", []):
            cols = [
                InterfaceColumn(
                    name=c["name"],
                    data_type=c.get("data_type", "unknown"),
                    description=c.get("description", ""),
                    required=c.get("required", True),
                )
                for c in m.get("columns", [])
            ]
            models.append(InterfaceModel(
                name=m["name"],
                access=m.get("access", "public"),
                version=m.get("version", 1),
                columns=cols,
                description=m.get("description", ""),
            ))
        return cls(
            project=data.get("project", ""),
            version=data.get("version", 1),
            published_at=data.get("published_at", ""),
            models=models,
        )

    def write(self, project_path: Path) -> None:
        data = {
            "interface": {
                "project": self.project,
                "version": self.version,
                "published_at": self.published_at,
                "models": [
                    {
                        "name": m.name,
                        "access": m.access,
                        "version": m.version,
                        "description": m.description,
                        "columns": [
                            {
                                "name": c.name,
                                "data_type": c.data_type,
                                "description": c.description,
                                "required": c.required,
                            }
                            for c in m.columns
                        ],
                    }
                    for m in self.models
                ],
            }
        }
        (project_path / "interface.yml").write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    def get_model(self, name: str) -> Optional[InterfaceModel]:
        for m in self.models:
            if m.name == name:
                return m
        return None

    def public_models(self) -> list[InterfaceModel]:
        return [m for m in self.models if m.access == "public"]


@dataclass
class ContractViolation:
    project: str
    model: str
    kind: str   # missing_column | type_mismatch | model_removed | access_downgrade
    detail: str


class ContractValidator:
    """Compare a published interface.yml against actual project state."""

    def validate(
        self,
        contract: ProducerContract,
        project_path: Path,
    ) -> list[ContractViolation]:
        """Check that every column in the interface is still present in schema.yml."""
        violations: list[ContractViolation] = []
        actual_schema = self._load_actual_schema(project_path)

        for interface_model in contract.models:
            actual = actual_schema.get(interface_model.name)
            if actual is None:
                violations.append(ContractViolation(
                    project=contract.project,
                    model=interface_model.name,
                    kind="model_removed",
                    detail=f"Model '{interface_model.name}' is in interface.yml but no longer in schema.yml",
                ))
                continue
            # Check access hasn't been downgraded
            actual_access = actual.get("access", "protected")
            if self._access_level(actual_access) < self._access_level(interface_model.access):
                violations.append(ContractViolation(
                    project=contract.project,
                    model=interface_model.name,
                    kind="access_downgrade",
                    detail=(
                        f"Access downgraded from '{interface_model.access}' "
                        f"to '{actual_access}' — downstream consumers may break"
                    ),
                ))
            # Check required columns still present
            actual_cols = {c["name"] for c in actual.get("columns", [])}
            for col in interface_model.required_columns():
                if col.name not in actual_cols and actual_cols:
                    violations.append(ContractViolation(
                        project=contract.project,
                        model=interface_model.name,
                        kind="missing_column",
                        detail=f"Required column '{col.name}' missing from '{interface_model.name}'",
                    ))

        return violations

    @staticmethod
    def _access_level(access: str) -> int:
        return {"private": 0, "protected": 1, "public": 2}.get(access, 1)

    def _load_actual_schema(self, project_path: Path) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for fname in ("schema.yml", "schema.yaml"):
            path = project_path / fname
            if not path.exists():
                path = project_path / "models" / fname
            if path.exists():
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                for m in raw.get("models", []):
                    result[m["name"]] = m
                return result
        # Also walk models/ subdirectory
        models_dir = project_path / "models"
        if models_dir.exists():
            for schema_file in list(models_dir.rglob("schema.yml")) + list(models_dir.rglob("schema.yaml")):
                raw = yaml.safe_load(schema_file.read_text(encoding="utf-8")) or {}
                for m in raw.get("models", []):
                    result[m["name"]] = m
        return result
