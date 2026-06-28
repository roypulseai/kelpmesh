import time
import typer
from pathlib import Path
from rich.console import Console
from kelpmesh.core.project import Project
from kelpmesh.core.executor import Executor
from kelpmesh.core.schema_yaml import SchemaYaml
from kelpmesh.state.engine import StateEngine
from kelpmesh.testing.runner import TestRunner
from kelpmesh.testing.schema_tests import SchemaTestGenerator
from kelpmesh.adapters import get_adapter

console = Console()

_STATUS_ICON = {
    "success": "[green]✓[/green]",
    "skipped": "[dim]–[/dim]",
    "failed": "[red]✗[/red]",
}


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
    wall_start = time.monotonic()

    def on_model_done(name: str, status: str, elapsed: float):
        icon = _STATUS_ICON.get(status, "?")
        timing = f"{elapsed:.2f}s" if elapsed > 0 else ""
        console.print(f"  {icon} {name:<40} {timing}")

    console.print(f"\n[bold]kelpmesh build[/bold]  [dim]{project.path.name}[/dim]\n")
    console.print("[dim]── models ──────────────────────────────────────────[/dim]")

    run_results = executor.run(models, progress_cb=on_model_done)

    # Tests
    console.print("\n[dim]── tests ───────────────────────────────────────────[/dim]")
    schema = SchemaYaml(project.path)
    schema_tests = SchemaTestGenerator(schema).all_tests(list(project.models.keys()))
    runner = TestRunner(adapter, schema_tests=schema_tests)
    tests_path = project.path / project.config.tests_path
    test_results = runner.run_all(tests_path)

    if test_results:
        for r in test_results:
            if r["passed"]:
                console.print(f"  [green]✓[/green] {r['name']:<40} [dim]0 failures[/dim]")
            else:
                sev = r.get("severity", "error")
                icon = "[yellow]![/yellow]" if sev == "warn" else "[red]✗[/red]"
                console.print(f"  {icon} {r['name']:<40} [red]{r['failures']} failures[/red]")
    else:
        console.print("  [dim]No tests found.[/dim]")

    wall_elapsed = time.monotonic() - wall_start
    n_ok = len(run_results["success"])
    n_skip = len(run_results["skipped"])
    n_fail = len(run_results["failed"])
    t_pass = sum(1 for r in test_results if r["passed"])
    t_fail = sum(1 for r in test_results if not r["passed"])

    console.print()
    run_parts = []
    if n_ok:
        run_parts.append(f"[green]{n_ok} succeeded[/green]")
    if n_skip:
        run_parts.append(f"[dim]{n_skip} skipped[/dim]")
    if n_fail:
        run_parts.append(f"[red]{n_fail} failed[/red]")

    test_parts = []
    if t_pass:
        test_parts.append(f"[green]{t_pass} passed[/green]")
    if t_fail:
        test_parts.append(f"[red]{t_fail} failed[/red]")

    console.print(
        f"[bold]Done[/bold]  models: {', '.join(run_parts) or '[dim]none[/dim]'}  "
        f"tests: {', '.join(test_parts) or '[dim]none[/dim]'}  "
        f"[dim]in {wall_elapsed:.2f}s[/dim]"
    )

    if run_results["failed"]:
        console.print()
        for item in run_results["failed"]:
            console.print(f"  [red]Error in {item['name']}:[/red] {item['error']}")

    total_failed = n_fail + t_fail
    adapter.disconnect()
    state.close()

    if total_failed > 0:
        raise typer.Exit(1)
