import typer
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from briq.core.project import Project
from briq.state.engine import StateEngine

console = Console()


def ls_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    project = Project(project_dir.resolve())
    state = StateEngine(project.path)

    if not project.models:
        console.print("[yellow]No models found in project.[/yellow]")
        raise typer.Exit(1)

    table = Table(title="briq models")
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
