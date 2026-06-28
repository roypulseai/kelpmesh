import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from briq.core.project import Project
from briq.core.executor import Executor
from briq.state.engine import StateEngine
from briq.testing.runner import TestRunner
from briq.adapters import get_adapter

console = Console()


def build_cmd(
    models: list[str] = typer.Argument(None, help="Model names to build"),
    project_dir: Path = typer.Option(
        ".", "--project-dir", "-p", help="Project directory"
    ),
    threads: int = typer.Option(4, "--threads", "-t", help="Number of threads"),
    full_refresh: bool = typer.Option(
        False, "--full-refresh", "-f", help="Ignore state and run all"
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

    console.print("Building models...")
    run_results = executor.run(models)

    run_table = Table(title="briq build - run results")
    run_table.add_column("Status", style="bold")
    run_table.add_column("Model", style="cyan")
    run_table.add_column("Details")

    for item in run_results["success"]:
        run_table.add_row("[green]OK[/green]", item["name"], "")
    for item in run_results["skipped"]:
        run_table.add_row("[blue]SKIP[/blue]", item["name"], "Up to date")
    for item in run_results["failed"]:
        run_table.add_row("[red]FAIL[/red]", item["name"], item["error"] or "Unknown error")

    console.print(run_table)

    runner = TestRunner(adapter)
    tests_path = project.path / project.config.tests_path
    test_results = runner.run_all(tests_path)

    if test_results:
        test_table = Table(title="briq build - test results")
        test_table.add_column("Test", style="cyan")
        test_table.add_column("Status", style="bold")
        test_table.add_column("Failures")

        passed = sum(1 for r in test_results if r["passed"])
        failed = sum(1 for r in test_results if not r["passed"])

        for r in test_results:
            status = "[green]PASS[/green]" if r["passed"] else "[red]FAIL[/red]"
            test_table.add_row(r["name"], status, str(r["failures"]))

        console.print(test_table)
        console.print(f"\n[bold]Tests:[/bold] {passed} passed, {failed} failed")

    total_failed = len(run_results["failed"]) + sum(
        1 for r in test_results if not r["passed"]
    )
    adapter.disconnect()
    state.close()

    if total_failed > 0:
        raise typer.Exit(1)
