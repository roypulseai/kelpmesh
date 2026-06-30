"""kelpmesh metric commands — listing and querying metrics."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kelpmesh.adapters import get_adapter
from kelpmesh.core.project import Project

metric_app = typer.Typer(help="Metric definitions and querying — subcommands: list, query")
console = Console()


@metric_app.command(name="list")
def metric_list_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """List all defined metrics."""
    project_path = project_dir.resolve()
    project = Project(project_path)

    if not project.metrics:
        console.print("[yellow]No metrics defined in metrics.yml[/yellow]")
        return

    table_disp = Table(title="Metrics")
    table_disp.add_column("Name")
    table_disp.add_column("Label")
    table_disp.add_column("Model")
    table_disp.add_column("Type")
    table_disp.add_column("Dimensions")
    table_disp.add_column("Description")

    for m in project.metrics.values():
        dims = ", ".join(m.dimensions) if m.dimensions else "—"
        table_disp.add_row(m.name, m.label, m.model, m.type, dims, m.description or "")

    console.print(table_disp)


@metric_app.command(name="query")
def metric_query_cmd(
    metrics: str = typer.Argument(..., help="Comma-separated metric names"),
    group_by: str = typer.Option(None, "--group-by", "-g", help="Comma-separated dimension columns"),
    where: str = typer.Option(None, "--where", "-w", help="WHERE clause filter"),
    order_by: str = typer.Option(None, "--order-by", "-o", help="ORDER BY clause"),
    limit: int = typer.Option(100, "--limit", "-l", help="Max rows"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """Query metrics from the semantic layer."""
    project_path = project_dir.resolve()
    project = Project(project_path)

    metric_names = [m.strip() for m in metrics.split(",")]
    selected = []
    for name in metric_names:
        if name not in project.metrics:
            console.print(f"[red]Metric not found: {name}[/red]")
            raise typer.Exit(1)
        selected.append(project.metrics[name])

    gb = [d.strip() for d in group_by.split(",")] if group_by else []
    ob = [o.strip() for o in order_by.split(",")] if order_by else []

    # Generate SQL for the first metric (simple query)
    sql = selected[0].generate_sql(group_by=gb, where=where, order_by=ob, limit=limit)

    adapter = get_adapter(project.config.warehouse, project_path=str(project_path))
    try:
        result = adapter.execute(sql)
        if not result:
            console.print("[yellow]No results[/yellow]")
            return

        table_disp = Table(title="Query Results")
        for key in result[0]:
            table_disp.add_column(key, style="cyan")
        for row in result:
            table_disp.add_row(*[str(v) if v is not None else "—" for v in row.values()])
        console.print(table_disp)
        console.print(f"\n[dim]{len(result)} row(s)[/dim]")
    except Exception as e:
        console.print(f"[red]Query error: {e}[/red]")
        console.print(f"[dim]Generated SQL:[/dim]\n{sql}")
        raise typer.Exit(1)
    finally:
        adapter.disconnect()
