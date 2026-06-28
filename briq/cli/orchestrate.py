import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from briq.orchestrate.engine import Orchestrator

console = Console()


def orchestrate_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Directory containing briq projects"),
    projects: list[str] = typer.Argument(None, help="Project names to run (default: all)"),
    full_refresh: bool = typer.Option(False, "--full-refresh", "-f", help="Reset state before run"),
):
    """Run multiple briq projects in dependency order."""
    orch = Orchestrator(project_dir)
    order = orch.execution_order()

    if not order:
        console.print("[yellow]No briq projects found in directory.[/yellow]")
        raise typer.Exit(1)

    console.print("[bold]Execution order:[/bold]")
    for i, name in enumerate(order, 1):
        deps = orch._depends_on(name)
        dep_str = f" (after: {', '.join(deps)})" if deps else ""
        console.print(f"  {i}. {name}{dep_str}")

    console.print()
    results = orch.run(project_names=projects, full_refresh=full_refresh)

    table = Table(title="Orchestration Results")
    table.add_column("Project", style="cyan")
    table.add_column("Depends On", style="bold")
    table.add_column("Ran", style="bold")
    table.add_column("Skipped", style="bold")
    table.add_column("Failed", style="bold")
    table.add_column("Status", style="bold")

    for p in results["projects"]:
        status = "[green]OK[/green]" if p["success"] else "[red]FAIL[/red]"
        deps = ", ".join(p["upstream_deps"]) or "-"
        table.add_row(p["name"], deps, str(p["ran"]), str(p["skipped"]), str(p["failed"]), status)

    console.print(table)

    if results["all_success"]:
        console.print("[green]All projects completed successfully.[/green]")
    else:
        console.print("[red]Some projects failed. Check logs above.[/red]")
        raise typer.Exit(1)
