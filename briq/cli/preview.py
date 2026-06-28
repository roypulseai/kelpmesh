import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from briq.core.project import Project
from briq.adapters import get_adapter
from briq.core.errors import sanitize_exception_message

console = Console(force_terminal=True, color_system=None, no_color=True)


def preview_cmd(
    model: str = typer.Argument(..., help="Model name to preview"),
    limit: int = typer.Option(100, "--limit", "-l", help="Number of rows"),
    project_dir: Path = typer.Option(
        ".", "--project-dir", "-p", help="Project directory"
    ),
):
    project = Project(project_dir.resolve())

    if model not in project.models:
        console.print(f"[red]Model '{model}' not found.[/red]")
        raise typer.Exit(1)

    adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
    model_obj = project.models[model]
    table_name = model_obj.alias or model

    try:
        rows = adapter.preview(f"SELECT * FROM {table_name}", limit=limit)
    except Exception as e:
        console.print(f"[red]Could not preview '{table_name}': {sanitize_exception_message(str(e))}[/red]")
        console.print("[yellow]Make sure the model has been run first with 'briq run'.[/yellow]")
        adapter.disconnect()
        raise typer.Exit(1)

    if not rows:
        console.print(f"[yellow]No data returned for '{model}'.[/yellow]")
        adapter.disconnect()
        return

    cols = list(rows[0].keys())
    table = Table(title=f"Preview: {model} ({len(rows)} rows)")
    for i, key in enumerate(cols):
        table.add_column(key, style="cyan" if i == 0 else "")
    for row in rows:
        table.add_row(*[str(v) if v is not None else "[dim]null[/dim]" for v in row.values()])

    console.print(table)
    adapter.disconnect()
