from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kelpmesh.adapters import get_adapter
from kelpmesh.core.project import Project
from kelpmesh.diff.engine import DiffEngine
from kelpmesh.state.engine import StateEngine

console = Console()


def diff_cmd(
    model: str = typer.Argument(..., help="Model name to diff"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """Compare model output against a previous run state.

    Examples:

        kelpmesh diff orders

        kelpmesh diff orders --project-dir /path/to/project
    """
    project = Project(project_dir.resolve())
    adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
    state = StateEngine(project.path)
    diff_engine = DiffEngine(project, adapter, state)

    result = diff_engine.compare(model)

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        adapter.disconnect()
        state.close()
        raise typer.Exit(1)

    table = Table(title=f"kelpmesh diff - {model}")
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value")

    table.add_row("Model", result["model"])
    table.add_row("Table", result["table"])
    table.add_row("Current row count", str(result["current_row_count"]))
    table.add_row("Previous row count", str(result["previous_row_count"]))
    table.add_row("Delta", str(result["row_count_delta"]))
    table.add_row("Changed", "YES" if result["has_changed"] else "NO")

    console.print(table)

    if result.get("sample_diffs"):
        diff_table = Table(title="Sample diffs")
        diff_table.add_column("Change", style="bold")
        for key in result["sample_diffs"][0]:
            diff_table.add_column(key)
        for row in result["sample_diffs"]:
            diff_table.add_row(*[str(v) for v in row.values()])
        console.print(diff_table)

    adapter.disconnect()
    state.close()
