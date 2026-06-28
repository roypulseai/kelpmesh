"""BriqOperator — execute kelpmesh commands as Airflow tasks."""
from airflow.models import BaseOperator
from airflow.utils.decorators import apply_defaults
from kelpmesh.core.project import Project
from kelpmesh.core.executor import Executor
from kelpmesh.state.engine import StateEngine
from kelpmesh.adapters import get_adapter


class BriqOperator(BaseOperator):
    """Execute a kelpmesh command (run, build, test) as an Airflow task.

    Args:
        briq_cmd: kelpmesh command to run ('run', 'build', 'test').
        project_dir: Path to the kelpmesh project directory.
        models: Optional list of model names to target.
        full_refresh: If True, ignore cached state.
        select: Optional selection syntax (+model, model+, @model).
    """

    @apply_defaults
    def __init__(
        self,
        briq_cmd: str = "build",
        project_dir: str = ".",
        models: list[str] | None = None,
        full_refresh: bool = False,
        select: list[str] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.briq_cmd = briq_cmd
        self.project_dir = project_dir
        self.models = models
        self.full_refresh = full_refresh
        self.select = select

    def execute(self, context):
        from pathlib import Path

        project_path = Path(self.project_dir).resolve()

        project = Project(project_path)
        adapter = get_adapter(project.config.warehouse, project_path=str(project_path))
        state = StateEngine(project_path)

        if self.full_refresh:
            state.reset()

        if self.briq_cmd in ("run", "build"):
            executor = Executor(project, adapter, state)
            results = executor.run(self.models, select=self.select)
            failed = results.get("failed", [])
            if failed:
                raise RuntimeError(
                    f"kelpmesh {self.briq_cmd} failed: "
                    + "; ".join(f"{m['name']}: {m['error']}" for m in failed)
                )

        if self.briq_cmd in ("test", "build"):
            from kelpmesh.testing.runner import TestRunner
            runner = TestRunner(adapter)
            tests_path = project_path / project.config.tests_path
            test_results = runner.run_all(tests_path)
            failed_tests = [r for r in test_results if not r["passed"]]
            if failed_tests:
                raise RuntimeError(
                    f"Tests failed: "
                    + "; ".join(f"{t['name']} ({t['failures']} failures)" for t in failed_tests)
                )

        adapter.disconnect()
        state.close()
        self.log.info("kelpmesh %s completed successfully", self.briq_cmd)
