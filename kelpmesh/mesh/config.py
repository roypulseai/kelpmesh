"""Mesh configuration — reads mesh.yml from the workspace root."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class MeshProject:
    name: str
    path: Path
    warehouse: str = "duckdb"
    group: str = "default"
    # Default access for models not explicitly configured
    default_access: str = "protected"  # private | protected | public

    def resolve_path(self, workspace_root: Path) -> Path:
        if self.path.is_absolute():
            return self.path
        return (workspace_root / self.path).resolve()

    def exists(self, workspace_root: Path) -> bool:
        return self.resolve_path(workspace_root).exists()


@dataclass
class MeshConfig:
    name: str
    projects: list[MeshProject] = field(default_factory=list)
    workspace_root: Path = field(default_factory=Path)

    @classmethod
    def load(cls, workspace_root: Path) -> "MeshConfig":
        for fname in ("mesh.yml", "mesh.yaml"):
            path = workspace_root / fname
            if path.exists():
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                return cls._from_dict(raw.get("mesh", raw), workspace_root)
        return cls(name="", workspace_root=workspace_root)

    @classmethod
    def _from_dict(cls, data: dict, workspace_root: Path) -> "MeshConfig":
        projects = []
        for p in data.get("projects", []):
            projects.append(MeshProject(
                name=p["name"],
                path=Path(p["path"]),
                warehouse=p.get("warehouse", "duckdb"),
                group=p.get("group", "default"),
                default_access=p.get("default_access", "protected"),
            ))
        return cls(
            name=data.get("name", ""),
            projects=projects,
            workspace_root=workspace_root,
        )

    def get_project(self, name: str) -> Optional[MeshProject]:
        for p in self.projects:
            if p.name == name:
                return p
        return None

    def project_names(self) -> list[str]:
        return [p.name for p in self.projects]

    def is_empty(self) -> bool:
        return not self.projects

    def write(self, workspace_root: Path) -> None:
        data = {
            "mesh": {
                "name": self.name,
                "projects": [
                    {
                        "name": p.name,
                        "path": str(p.path),
                        "warehouse": p.warehouse,
                        "group": p.group,
                        "default_access": p.default_access,
                    }
                    for p in self.projects
                ],
            }
        }
        (workspace_root / "mesh.yml").write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
