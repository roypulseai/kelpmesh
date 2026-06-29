import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from kelpmesh.core.project import Project
from kelpmesh.diff.comparison import ComparisonEngine
from kelpmesh.adapters import get_adapter

console = Console()


def compare_cmd(
    models: list[str] = typer.Argument(None, help="Model names to compare"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    dbt_project_dir: Path | None = typer.Option(None, "--dbt", help="Path to dbt project for comparison"),
):
    """Compare kelpmesh model output against dbt output row-by-row."""
    project_path = project_dir.resolve()
    project = Project(project_path)
    kelpmesh_adapter = get_adapter(project.config.warehouse, project_path=str(project_path))

    dbt_adapter = None
    if dbt_project_dir:
        dbt_path = dbt_project_dir.resolve()
        dbt_project = Project(dbt_path)
        dbt_adapter = get_adapter(dbt_project.config.warehouse, project_path=str(dbt_path))

    engine = ComparisonEngine(project, kelpmesh_adapter, dbt_adapter)

    model_list = models or sorted(project.models.keys())
    all_match = True

    table = Table(title="kelpmesh compare")
    table.add_column("Model", style="cyan")
    table.add_column("kelpmesh rows", style="bold")
    table.add_column("dbt rows", style="bold")
    table.add_column("Match", style="bold")
    table.add_column("Notes")

    for name in model_list:
        result = engine.compare(name)
        if "error" in result:
            table.add_row(name, "-", "-", "[red]ERROR[/red]", result["error"])
            all_match = False
            continue
        match_str = "[green]YES[/green]" if result["match"] else "[red]NO[/red]"
        notes = "; ".join(result.get("differences", []))
        kelpmesh_rows = str(result["kelpmesh_row_count"])
        dbt_rows = str(result["dbt_row_count"])
        table.add_row(name, kelpmesh_rows, dbt_rows, match_str, notes)
        if not result["match"]:
            all_match = False

    console.print(table)
    if dbt_adapter:
        dbt_adapter.disconnect()
    kelpmesh_adapter.disconnect()

    if all_match and dbt_project_dir:
        console.print("[green]All models produce identical output![/green]")
    elif not all_match:
        console.print("[yellow]Some models differ between kelpmesh and dbt.[/yellow]")
        raise typer.Exit(1)
