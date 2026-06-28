"""Mesh health checker — validates the whole project graph."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kelpmesh.mesh.config import MeshConfig, MeshProject
from kelpmesh.mesh.resolver import MeshResolver, CrossProjectRef
from kelpmesh.mesh.access import AccessChecker
from kelpmesh.mesh.contracts import ProducerContract, ContractValidator, ContractViolation


@dataclass
class ProjectHealth:
    name: str
    path_exists: bool
    cross_refs: list[CrossProjectRef] = field(default_factory=list)
    access_violations: list[dict] = field(default_factory=list)
    contract_violations: list[ContractViolation] = field(default_factory=list)
    missing_ref_errors: list[dict] = field(default_factory=list)
    has_interface: bool = False

    @property
    def healthy(self) -> bool:
        return (
            self.path_exists
            and not self.access_violations
            and not self.contract_violations
            and not self.missing_ref_errors
        )

    @property
    def status(self) -> str:
        if not self.path_exists:
            return "missing"
        total_issues = (
            len(self.access_violations)
            + len(self.contract_violations)
            + len(self.missing_ref_errors)
        )
        if total_issues == 0:
            return "healthy"
        if total_issues <= 2:
            return "warn"
        return "error"


@dataclass
class MeshHealthReport:
    mesh_name: str
    project_count: int
    project_health: list[ProjectHealth] = field(default_factory=list)

    @property
    def healthy_count(self) -> int:
        return sum(1 for p in self.project_health if p.healthy)

    @property
    def total_issues(self) -> int:
        return sum(
            len(p.access_violations) + len(p.contract_violations) + len(p.missing_ref_errors)
            for p in self.project_health
        )

    @property
    def all_healthy(self) -> bool:
        return self.total_issues == 0 and all(p.path_exists for p in self.project_health)


class MeshHealthChecker:
    """Run a full health check across all projects in the mesh."""

    def __init__(self, config: MeshConfig):
        self.config = config
        self.resolver = MeshResolver(config)
        self.validator = ContractValidator()

    def check(self) -> MeshHealthReport:
        report = MeshHealthReport(
            mesh_name=self.config.name,
            project_count=len(self.config.projects),
        )
        for proj in self.config.projects:
            report.project_health.append(self._check_project(proj))
        return report

    def check_project(self, project_name: str) -> Optional[ProjectHealth]:
        proj = self.config.get_project(project_name)
        if proj is None:
            return None
        return self._check_project(proj)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _check_project(self, proj: MeshProject) -> ProjectHealth:
        workspace = self.config.workspace_root
        proj_path = proj.resolve_path(workspace)
        health = ProjectHealth(name=proj.name, path_exists=proj_path.exists())

        if not health.path_exists:
            return health

        # 1. Collect all cross-project refs used by this project's models
        cross_refs = self._collect_cross_refs(proj_path)
        health.cross_refs = cross_refs

        # 2. Validate ref targets exist in mesh
        health.missing_ref_errors = self.resolver.validate_refs(cross_refs, workspace)

        # 3. Check access policies
        for ref in cross_refs:
            target_proj = self.config.get_project(ref.project)
            if target_proj is None:
                continue
            target_path = target_proj.resolve_path(workspace)
            if not target_path.exists():
                continue
            checker = AccessChecker(target_path, project_group=target_proj.group)
            allowed, reason = checker.can_reference(
                ref.model,
                referencing_group=proj.group,
                default_access=target_proj.default_access,
            )
            if not allowed:
                health.access_violations.append({
                    "ref": ref.raw,
                    "reason": reason,
                })

        # 4. Contract validation
        contract = ProducerContract.load(proj_path)
        health.has_interface = contract is not None
        if contract:
            violations = self.validator.validate(contract, proj_path)
            health.contract_violations = violations

        return health

    def _collect_cross_refs(self, proj_path: Path) -> list[CrossProjectRef]:
        from kelpmesh.parser.sql import SQLParser
        parser = SQLParser()
        refs: list[CrossProjectRef] = []
        seen: set[str] = set()

        models_dir = proj_path / "models"
        if not models_dir.exists():
            models_dir = proj_path

        for sql_file in models_dir.rglob("*.sql"):
            try:
                sql = sql_file.read_text(encoding="utf-8")
                tables = parser.extract_table_references(sql)
                for t in tables:
                    if t not in seen and self.resolver.is_cross_ref(t):
                        seen.add(t)
                        parsed = self.resolver.parse(t)
                        if parsed:
                            refs.append(parsed)
            except Exception:
                continue

        return refs

    def cross_project_graph(self) -> dict[str, list[str]]:
        """Return adjacency dict: project → [projects it depends on]."""
        graph: dict[str, list[str]] = {p.name: [] for p in self.config.projects}
        for proj in self.config.projects:
            proj_path = proj.resolve_path(self.config.workspace_root)
            if not proj_path.exists():
                continue
            refs = self._collect_cross_refs(proj_path)
            for r in refs:
                if r.project in graph and r.project not in graph[proj.name]:
                    graph[proj.name].append(r.project)
        return graph
