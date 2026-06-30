import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from kelpmesh.adapters import get_adapter
from kelpmesh.core.executor import Executor
from kelpmesh.core.project import Project
from kelpmesh.state.engine import StateEngine

console = Console()

_STATUS_ICON = {
    "success": "[green]✓[/green]",
    "skipped": "[dim]–[/dim]",
    "failed": "[red]✗[/red]",
}


def _make_summary_table(rows: list[tuple]) -> Table:
    table = Table(box=None, padding=(0, 1), show_header=False)
    table.add_column("icon", no_wrap=True, width=3)
    table.add_column("model", style="cyan", no_wrap=True)
    table.add_column("timing", style="dim", no_wrap=True, justify="right")
    table.add_column("detail", style="dim")
    for icon, name, timing, detail in rows:
        table.add_row(Text.from_markup(icon), name, timing, detail)
    return table


def run_cmd(
    models: list[str] = typer.Argument(None, help="Model names to run"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    threads: int = typer.Option(4, "--threads", "-t", help="Number of threads"),
    full_refresh: bool = typer.Option(False, "--full-refresh", "-f", help="Force full rebuild of incremental models"),
    select: list[str] = typer.Option(
        None, "--select", "-s", help="Model selection (+upstream, model+downstream, @full, tag:name)"
    ),
    tag: list[str] = typer.Option(
        None, "--tag", help="Run all models with this tag (repeatable)"
    ),
    var: list[str] = typer.Option(
        None, "--var", help="Set a variable: key=value (repeatable, overrides kelpmesh.yml vars)"
    ),
    changed: bool = typer.Option(
        False, "--changed", "-c", help="Only run models changed vs base branch (slim CI)"
    ),
    changed_against: str = typer.Option(
        None, "--changed-against", help="Base branch/ref for --changed (default: auto-detect)"
    ),
    defer: str = typer.Option(
        None, "--defer", "-d", help="Defer to production state DB path"
    ),
    env: Optional[str] = typer.Option(
        None, "--env", "-e", help="Target environment (dev/staging/prod) — prefixes all table names"
    ),
    target: Optional[str] = typer.Option(
        None, "--target", help="Active profile from kelpmesh.yml targets (dev/staging/prod)"
    ),
    fail_fast: bool = typer.Option(
        False, "--fail-fast", help="Stop execution on the first model failure"
    ),
    slack_webhook: Optional[str] = typer.Option(
        None, "--slack-webhook", help="Slack webhook URL for failure alerts"
    ),
    alert_webhook: Optional[str] = typer.Option(
        None, "--alert-webhook", help="Generic webhook URL for failure alerts"
    ),
):
    """Execute models — build tables, views, and incremental models against the warehouse.

    Examples:

        kelpmesh run

        kelpmesh run orders

        kelpmesh run --select +orders --env dev

        kelpmesh run --changed --defer target_prod
    """
    from kelpmesh.core.config import ProjectConfig
    from kelpmesh.core.substitutions import parse_cli_vars

    project_path = project_dir.resolve()
    config = ProjectConfig.load(project_path, target=target)
    project = Project(project_path)
    project.config = config  # apply resolved target config

    if not project.models:
        console.print("[yellow]No models found in project.[/yellow]")
        raise typer.Exit(1)

    adapter = get_adapter(config.warehouse, project_path=str(project.path))
    state = StateEngine(project.path)

    if full_refresh:
        state.reset()

    cli_vars = parse_cli_vars(list(var) if var else [])

    from kelpmesh.core.schema_yaml import SchemaYaml
    from kelpmesh.observability.history import RunHistory
    schema_yaml = SchemaYaml(project.path)
    run_history = RunHistory(project.path)
    executor = Executor(
        project, adapter, state, threads=threads,
        schema_yaml=schema_yaml, env=env, run_history=run_history,
        vars=cli_vars, full_refresh=full_refresh, fail_fast=fail_fast,
    )

    rows: list[tuple] = []
    wall_start = time.monotonic()

    def on_model_done(name: str, status: str, elapsed: float):
        icon = _STATUS_ICON.get(status, "?")
        timing = f"{elapsed:.2f}s" if elapsed >= 0.01 else "<0.01s" if elapsed > 0 else ""
        detail = ""
        rows.append((icon, name, timing, detail))
        console.print(f"  {icon} {name:<40} {timing}")

    console.print(f"\n[bold]kelpmesh run[/bold]  [dim]{project.path.name}[/dim]\n")

    results = executor.run(
        models,
        select=select or None,
        tags=list(tag) if tag else None,
        changed=changed,
        changed_against=changed_against or None,
        defer=defer or None,
        progress_cb=on_model_done,
    )

    wall_elapsed = time.monotonic() - wall_start
    n_ok = len(results["success"])
    n_skip = len(results["skipped"])
    n_fail = len(results["failed"])

    console.print()
    parts = []
    if n_ok:
        parts.append(f"[green]{n_ok} succeeded[/green]")
    if n_skip:
        parts.append(f"[dim]{n_skip} skipped[/dim]")
    if n_fail:
        parts.append(f"[red]{n_fail} failed[/red]")
    wall_timing = f"{wall_elapsed:.2f}s" if wall_elapsed >= 0.01 else "<0.01s"
    console.print(f"[bold]Done[/bold]  {', '.join(parts)}  [dim]in {wall_timing}[/dim]")

    if results["failed"]:
        console.print()
        for item in results["failed"]:
            console.print(f"  [red]Error in {item['name']}:[/red] {item['error']}")

    run_history.close()
    adapter.disconnect()
    state.close()

    # Send alerts if configured
    if (slack_webhook or alert_webhook) and results["failed"]:
        from kelpmesh.observability.alerts import RunSummary, send_slack_alert, send_webhook_alert
        summary = RunSummary(
            project_name=project.path.name,
            env=env or "default",
            succeeded=[r["name"] for r in results["success"]],
            skipped=[r["name"] for r in results["skipped"]],
            failed=results["failed"],
            anomalies=[],
            elapsed_s=wall_elapsed,
        )
        if slack_webhook:
            send_slack_alert(slack_webhook, summary)
        if alert_webhook:
            send_webhook_alert(alert_webhook, summary)

    if results["failed"]:
        raise typer.Exit(1)
