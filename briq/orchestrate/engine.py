"""Multi-project orchestration — run projects in dependency order across repositories."""
import logging
from pathlib import Path
from typing import Optional
from briq.core.project import Project
from briq.core.executor import Executor
from briq.state.engine import StateEngine
from briq.adapters import get_adapter

_logger = logging.getLogger(__name__)


class Orchestrator:
    """Orchestrates runs across multiple briq projects respecting cross-project dependencies.

    Projects declare upstream project dependencies in briq.yml:
        depends_on:
          - upstream_project
    """

    def __init__(self, projects_dir: Path):
        self.projects_dir = projects_dir.resolve()
        self.projects: dict[str, Project] = {}
        self._load_projects()

    def _load_projects(self):
        for child in sorted(self.projects_dir.iterdir()):
            if child.is_dir() and (child / "briq.yml").exists():
                try:
                    self.projects[child.name] = Project(child)
                except Exception as e:
                    _logger.debug("Skipping invalid project %s: %s", child.name, e)

    def _depends_on(self, name: str) -> list[str]:
        project = self.projects.get(name)
        if project:
            return getattr(project.config, "depends_on", []) or []
        return []

    def execution_order(self) -> list[str]:
        """Topological sort of projects by cross-project dependencies."""
        visited = set()
        order = []

        def visit(name: str):
            if name in visited:
                return
            visited.add(name)
            for dep in self._depends_on(name):
                if dep in self.projects:
                    visit(dep)
            order.append(name)

        for name in self.projects:
            visit(name)

        return order

    def run(self, project_names: Optional[list[str]] = None, full_refresh: bool = False) -> dict:
        """Run all or selected projects in dependency order."""
        if project_names:
            names = [n for n in self.execution_order() if n in project_names]
        else:
            names = self.execution_order()

        results = {"projects": []}
        for name in names:
            project = self.projects.get(name)
            if not project:
                continue
            adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
            state = StateEngine(project.path)
            if full_refresh:
                state.reset()
            executor = Executor(project, adapter, state)
            run_results = executor.run()
            adapter.disconnect()
            state.close()
            results["projects"].append({
                "name": name,
                "upstream_deps": self._depends_on(name),
                "success": len(run_results.get("failed", [])) == 0,
                "ran": len(run_results.get("ran", [])),
                "skipped": len(run_results.get("skipped", [])),
                "failed": len(run_results.get("failed", [])),
            })

        results["all_success"] = all(p["success"] for p in results["projects"])
        return results
