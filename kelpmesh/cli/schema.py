import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from kelpmesh.core.project import Project
from kelpmesh.state.engine import StateEngine
from kelpmesh.schema.drift import SchemaDriftDetector
from kelpmesh.adapters import get_adapter

console = Console(force_terminal=True)


def schema_cmd(
    diff: str = typer.Argument(None, help="Model name to check"),
    project_dir: Path = typer.Option(
        ".", "--project-dir", "-p", help="Project directory"
    ),
):
    project = Project(project_dir.resolve())
    adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
    state = StateEngine(project.path)
    detector = SchemaDriftDetector(project, state)

    if diff:
        result = detector.check_model(diff, adapter)
        if not result:
            console.print(f"[yellow]No schema info for '{diff}'. Run the model first.[/yellow]")
            adapter.disconnect()
            state.close()
            raise typer.Exit(1)
        results = [result]
    else:
        results = detector.check_all(adapter)

    drift_found = False
    for r in results:
        if r["status"] == "drift_detected":
            drift_found = True
            table = Table(title=f"Schema drift detected: {r['model']} ({r['table']})")
            table.add_column("Type", style="bold")
            table.add_column("Column")
            table.add_column("Details")
            for c in r["changes"]:
                if c["type"] == "added":
                    table.add_row("[green]+ added[/green]", c["column"], c.get("data_type", ""))
                elif c["type"] == "removed":
                    table.add_row("[red]- removed[/red]", c["column"], "")
                elif c["type"] == "changed":
                    table.add_row(
                        "[yellow]~ changed[/yellow]",
                        c["column"],
                        f"{c['from_type']} -> {c['to_type']}",
                    )
            console.print(table)
        elif r["status"] == "first_checked":
            console.print(
                f"[dim]{r['model']}: first schema check "
                f"({r['current_columns']} columns)[/dim]"
            )

    if not drift_found and results:
        console.print("[green]No schema drift detected.[/green]")

    adapter.disconnect()
    state.close()

    if drift_found:
        raise typer.Exit(1)
