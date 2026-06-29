"""Validate SQL files and detect circular dependencies."""
import sys
from pathlib import Path

import typer

from kelpmesh.core.errors import sanitize_exception_message


def pre_commit_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """Validate SQL files and detect circular dependencies for pre-commit hooks."""
    project_dir = project_dir.resolve()
    models_dir = project_dir / "models"
    if not models_dir.exists():
        print("No models/ directory found.")
        sys.exit(0)

    sql_files = list(models_dir.rglob("*.sql"))
    if not sql_files:
        print("No SQL files found.")
        sys.exit(0)

    has_errors = False
    for f in sql_files:
        try:
            text = f.read_text(encoding="utf-8")
            if not text.strip():
                print(f"[warn] Empty SQL file: {f.relative_to(project_dir)}")
        except Exception as e:
            print(f"[error] Cannot read {f.relative_to(project_dir)}: {sanitize_exception_message(str(e))}")
            has_errors = True

    try:
        from kelpmesh.core.graph import DAGBuilder
        from kelpmesh.core.project import Project
        project = Project(project_dir)
        if project.models:
            dag = DAGBuilder(project)
            try:
                dag.execution_order()
                print(f"[ok] {len(project.models)} models, no cycles detected")
            except ValueError as e:
                print(f"[error] {e}")
                has_errors = True
    except Exception as e:
        print(f"[error] Failed to validate project: {sanitize_exception_message(str(e))}")
        has_errors = True

    if has_errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    pre_commit_cmd()
