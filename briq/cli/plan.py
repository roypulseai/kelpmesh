"""briq plan — show what would run, be skipped, and why (dry run)."""

from __future__ import annotations

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

_ACTION_STYLE = {
    "RUN": "green",
    "SKIP": "dim",
    "STALE": "yellow",
    "NEW": "cyan",
}


def plan_cmd(
    models: list[str] = typer.Argument(None, help="Model names to plan"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    select: list[str] = typer.Option(None, "--select", "-s", help="Model selection"),
    full_refresh: bool = typer.Option(False, "--full-refresh", "-f", help="Ignore state"),
    env: Optional[str] = typer.Option(None, "--env", "-e", help="Target environment (dev/staging/prod)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Preview the execution plan without running any models.

    Shows each model, the action briq would take (RUN / SKIP / NEW), the
    materialization type, its direct upstream dependencies, and the reason for
    the action.

    Example:
        briq plan
        briq plan --select +orders --env dev
    """
    import json as _json
    from briq.core.project import Project
    from briq.core.executor import Executor
    from briq.state.engine import StateEngine
    from briq.adapters import get_adapter

    project = Project(project_dir.resolve())

    if not project.models:
        console.print("[yellow]No models found in project.[/yellow]")
        raise typer.Exit(0)

    state = StateEngine(project.path)
    adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
    executor = Executor(project, adapter, state)

    dag = executor.dag
    dag.build()

    if select:
        model_names = dag.select_models(select)
    elif models:
        model_names = models
    else:
        model_names = dag.execution_order()

    plan_rows = []
    for name in model_names:
        model = project.get_model(name)
        if not model:
            continue

        model_hash = executor.compute_model_hash(name)
        stored_hash = state.get_hash(name)

        if full_refresh or stored_hash is None:
            action = "NEW" if stored_hash is None else "RUN"
            reason = "new model" if stored_hash is None else "--full-refresh"
        elif stored_hash == model_hash:
            action = "SKIP"
            reason = "up to date"
        else:
            action = "RUN"
            reason = "model changed"

        mat = model.materialized
        upstream = sorted(u for u in model.upstream if u in project.models)
        table_name = (f"{env}_" if env else "") + (model.alias or name)

        plan_rows.append({
            "name": name,
            "action": action,
            "materialized": mat,
            "table_name": table_name,
            "upstream": upstream,
            "reason": reason,
        })

    state.close()
    adapter.disconnect()

    if json_output:
        typer.echo(_json.dumps(plan_rows, indent=2))
        return

    # Summary counts
    counts = {"RUN": 0, "SKIP": 0, "NEW": 0, "STALE": 0}
    for r in plan_rows:
        counts[r["action"]] = counts.get(r["action"], 0) + 1

    env_label = f" [dim](env: {env})[/dim]" if env else ""
    console.print(f"\n[bold]briq plan[/bold]  [dim]{project.path.name}[/dim]{env_label}\n")

    table = Table(box=None, padding=(0, 1), show_header=True, header_style="bold dim")
    table.add_column("action", width=6)
    table.add_column("model", style="cyan")
    table.add_column("type", style="dim", width=12)
    table.add_column("table name", style="dim")
    table.add_column("upstream", style="dim")
    table.add_column("reason", style="dim italic")

    for r in plan_rows:
        style = _ACTION_STYLE.get(r["action"], "")
        ups = ", ".join(r["upstream"]) if r["upstream"] else "—"
        table.add_row(
            Text(r["action"], style=style),
            r["name"],
            r["materialized"],
            r["table_name"],
            ups,
            r["reason"],
        )

    console.print(table)
    console.print()

    parts = []
    if counts["RUN"]:
        parts.append(f"[green]{counts['RUN']} to run[/green]")
    if counts["NEW"]:
        parts.append(f"[cyan]{counts['NEW']} new[/cyan]")
    if counts["SKIP"]:
        parts.append(f"[dim]{counts['SKIP']} to skip[/dim]")
    console.print("  " + " · ".join(parts) if parts else "  Nothing to do.")
    console.print()
