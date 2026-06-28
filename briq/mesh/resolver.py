"""Cross-project reference resolver.

Convention: a SQL table name of the form  ``projectname__modelname``
(double underscore) signals a cross-project reference.  The resolver
expands these to the actual table name used in the target warehouse.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_CROSS_REF_RE = re.compile(r"^([a-z][a-z0-9_]*)__([a-z][a-z0-9_]*)$")


@dataclass
class CrossProjectRef:
    project: str
    model: str
    raw: str          # original token from SQL, e.g. "core__dim_customers"
    resolved: str = ""  # actual table name after resolution


class MeshResolver:
    """Detect and resolve ``project__model`` references across projects.

    Usage::

        resolver = MeshResolver(mesh_config)
        # At project load time — enrich model.upstream
        external = resolver.extract_cross_refs(model.upstream)
        # At execution time — rewrite SQL
        sql = resolver.rewrite_sql(sql)
    """

    def __init__(self, mesh_config=None):
        self._config = mesh_config  # MeshConfig | None
        self._resolved: dict[str, str] = {}   # raw_ref → actual_table
        self._build_resolution_map()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def is_cross_ref(self, name: str) -> bool:
        return bool(_CROSS_REF_RE.match(name))

    def parse(self, name: str) -> Optional[CrossProjectRef]:
        m = _CROSS_REF_RE.match(name)
        if not m:
            return None
        project, model = m.group(1), m.group(2)
        resolved = self._resolved.get(name, model)
        return CrossProjectRef(project=project, model=model, raw=name, resolved=resolved)

    def extract_cross_refs(self, names: set[str]) -> list[CrossProjectRef]:
        refs = []
        for n in names:
            r = self.parse(n)
            if r:
                refs.append(r)
        return refs

    def rewrite_sql(self, sql: str, env: str | None = None) -> str:
        """Replace all ``project__model`` tokens with their resolved table names."""
        if not self._resolved:
            return sql

        def _replace(match):
            raw = match.group(0)
            resolved = self._resolved.get(raw)
            if resolved is None:
                return raw
            if env and env != "default":
                return f"{env}_{resolved}"
            return resolved

        pattern = "|".join(re.escape(k) for k in sorted(self._resolved, key=len, reverse=True))
        if not pattern:
            return sql
        return re.sub(pattern, _replace, sql)

    def validate_refs(
        self,
        refs: list[CrossProjectRef],
        workspace_root: Path,
    ) -> list[dict]:
        """Return a list of validation errors (empty = all good)."""
        errors: list[dict] = []
        if self._config is None:
            for r in refs:
                errors.append({
                    "ref": r.raw,
                    "error": "No mesh.yml found — cross-project refs require a mesh configuration",
                })
            return errors

        for r in refs:
            proj = self._config.get_project(r.project)
            if proj is None:
                errors.append({
                    "ref": r.raw,
                    "error": f"Project '{r.project}' not in mesh.yml",
                })
                continue
            proj_path = proj.resolve_path(workspace_root)
            if not proj_path.exists():
                errors.append({
                    "ref": r.raw,
                    "error": f"Project path '{proj_path}' does not exist",
                })
        return errors

    def known_projects(self) -> list[str]:
        if self._config:
            return self._config.project_names()
        return []

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    def _build_resolution_map(self) -> None:
        """Populate _resolved: raw → actual_table_name."""
        if self._config is None:
            return
        for proj in self._config.projects:
            proj_path = proj.resolve_path(self._config.workspace_root)
            if not proj_path.exists():
                continue
            # Scan models directory for .sql files
            models_dir = proj_path / "models"
            if not models_dir.exists():
                models_dir = proj_path  # fallback
            for sql_file in models_dir.rglob("*.sql"):
                model_name = sql_file.stem
                raw = f"{proj.name}__{model_name}"
                self._resolved[raw] = model_name

    def add_mapping(self, raw: str, resolved: str) -> None:
        """Manually register a raw→resolved mapping (useful in tests)."""
        self._resolved[raw] = resolved
