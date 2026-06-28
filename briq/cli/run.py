import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from briq.core.project import Project
from briq.core.executor import Executor
from briq.state.engine import StateEngine
from briq.adapters import get_adapter

console = Console()


def run_cmd(
    models: list[str] = typer.Argument(None, help="Model names to run"),
    project_dir: Path = typer.Option(
        ".", "--project-dir", "-p", help="Project directory"
    ),
    threads: int = typer.Option(4, "--threads", "-t", help="Number of threads"),
    full_refresh: bool = typer.Option(
        False, "--full-refresh", "-f", help="Ignore state and run all"
    ),
    select: list[str] = typer.Option(
        None, "--select", "-s", help="Model selection (+upstream, model+downstream, @full)"
    ),
    changed: bool = typer.Option(
        False, "--changed", "-c", help="Only run models changed vs base branch (slim CI)"
    ),
    changed_against: str = typer.Option(
        None, "--changed-against", help="Base branch/ref for --changed (default: auto-detect)"
    ),
    defer: str = typer.Option(
        None, "--defer", "-d", help="Defer to production state DB path (skip models with matching hash)"
    ),
):
    project = Project(project_dir.resolve())

    if not project.models:
        console.print("[yellow]No models found in project.[/yellow]")
        raise typer.Exit(1)

    adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
    state = StateEngine(project.path)

    if full_refresh:
        state.reset()

    executor = Executor(project, adapter, state, threads=threads)

    console.print("Running models...")
    results = executor.run(
        models,
        select=select,
        changed=changed,
        changed_against=changed_against or None,
        defer=defer or None,
    )

    table = Table(title="briq run results")
    table.add_column("Status", style="bold")
    table.add_column("Model", style="cyan")
    table.add_column("Details")

    for item in results["success"]:
        table.add_row("[green]OK[/green]", item["name"], "")
    for item in results["skipped"]:
        table.add_row("[blue]SKIP[/blue]", item["name"], item["error"] or "Up to date")
    for item in results["failed"]:
        table.add_row("[red]FAIL[/red]", item["name"], item["error"] or "Unknown error")

    console.print(table)
    console.print(
        f"\n[bold]Summary:[/bold] "
        f"{len(results['success'])} succeeded, "
        f"{len(results['skipped'])} skipped, "
        f"{len(results['failed'])} failed"
    )

    adapter.disconnect()
    state.close()

    if results["failed"]:
        raise typer.Exit(1)
