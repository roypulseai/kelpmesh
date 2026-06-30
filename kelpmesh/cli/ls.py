from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kelpmesh.core.project import Project
from kelpmesh.state.engine import StateEngine

console = Console()


def ls_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """List all models in the project with their materialization type and status.

    Examples:

        kelpmesh ls

        kelpmesh ls --project-dir /path/to/project
    """
    project = Project(project_dir.resolve())
    state = StateEngine(project.path)

    if not project.models:
        console.print("[yellow]No models found in project.[/yellow]")
        raise typer.Exit(1)

    table = Table(title="kelpmesh models")
    table.add_column("Model", style="cyan")
    table.add_column("Type", style="bold")
    table.add_column("Status", style="bold")
    table.add_column("Upstream")
    table.add_column("Downstream")
    table.add_column("Last Run")

    for name in sorted(project.models.keys()):
        model = project.models[name]
        s = state.get_state(name)
        if s:
            status = "[green]Up-to-date[/green]"
            last_run = s.get("last_run_at", "")
        else:
            status = "[yellow]Never run[/yellow]"
            last_run = "-"
        mat = model.materialized
        upstream = str(len(model.upstream)) if model.upstream else "-"
        downstream = str(len(model.downstream)) if model.downstream else "-"
        table.add_row(name, mat, status, upstream, downstream, last_run)

    console.print(table)
    state.close()
