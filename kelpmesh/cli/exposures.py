"""kelpmesh exposure commands — listing downstream consumers."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kelpmesh.core.project import Project

exposure_app = typer.Typer(help="Exposure definitions — subcommands: list")
console = Console()


@exposure_app.command(name="list")
def exposure_list_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """List all defined exposures."""
    project_path = project_dir.resolve()
    project = Project(project_path)

    if not project.exposures:
        console.print("[yellow]No exposures defined in exposures.yml[/yellow]")
        return

    table_disp = Table(title="Exposures")
    table_disp.add_column("Name")
    table_disp.add_column("Type")
    table_disp.add_column("Owner")
    table_disp.add_column("Depends On")
    table_disp.add_column("URL")
    table_disp.add_column("Description")

    for exp in project.exposures.values():
        deps = ", ".join(exp.depends_on) if exp.depends_on else "—"
        table_disp.add_row(exp.name, exp.type, exp.owner, deps, exp.url or "—", exp.description or "")

    console.print(table_disp)
