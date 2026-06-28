"""kelpmesh plan — show what would run, be skipped, and why (dry run).

Unlike any feature in dbt Core or SQLmesh, kelpmesh plan gives you a Terraform-style
preview: every model, its current state, what action kelpmesh would take, and how many
downstream models would be affected — before a single warehouse query runs.
"""

from __future__ import annotations

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

_ACTION_STYLE = {
    "RUN":     "green",
    "NEW":     "cyan",
    "SKIP":    "dim",
    "STALE":   "yellow",
    "DISABLED": "dim red",
    "ANALYSIS": "dim",
}

_ACTION_ICON = {
    "RUN":     "●",
    "NEW":     "◆",
    "SKIP":    "○",
    "STALE":   "◐",
    "DISABLED": "✗",
    "ANALYSIS": "◇",
}


def plan_cmd(
    models: list[str] = typer.Argument(None, help="Model names to plan"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    select: list[str] = typer.Option(None, "--select", "-s", help="Model selection"),
    tag: list[str] = typer.Option(None, "--tag", help="Filter by tag"),
    var: list[str] = typer.Option(None, "--var", help="Set a variable: key=value"),
    full_refresh: bool = typer.Option(False, "--full-refresh", "-f", help="Treat incremental as table"),
    env: Optional[str] = typer.Option(None, "--env", "-e", help="Target environment"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Preview the execution plan without running any models.

    Shows each model, the action kelpmesh would take (RUN / SKIP / NEW / STALE),
    its materialization type, direct upstream dependencies, reason for action,
    and how many downstream models would be affected.

    This is a dry-run — nothing is executed in the warehouse.

    Examples:
        kelpmesh plan
        kelpmesh plan --select +orders --env dev
        kelpmesh plan --tag finance --var start_date=2025-01-01
    """
    import json as _json
    from kelpmesh.core.project import Project
    from kelpmesh.core.executor import Executor
    from kelpmesh.core.substitutions import parse_cli_vars
    from kelpmesh.state.engine import StateEngine
    from kelpmesh.adapters import get_adapter

    project = Project(project_dir.resolve())

    if not project.models:
        console.print("[yellow]No models found in project.[/yellow]")
        raise typer.Exit(0)

    cli_vars = parse_cli_vars(list(var) if var else [])
    state = StateEngine(project.path)
    adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
    executor = Executor(project, adapter, state, vars=cli_vars, full_refresh=full_refresh)

    dag = executor.dag
    dag.build()

    if select or tag:
        model_names = dag.select_models(
            select=list(select) if select else None,
            tags=list(tag) if tag else None,
        )
    elif models:
        model_names = models
    else:
        model_names = dag.execution_order()

    plan_rows = []
    for name in model_names:
        model = project.get_model(name)
        if not model:
            continue

        if not model.enabled:
            action, reason = "DISABLED", "enabled: false"
        elif model.materialized == "analysis":
            action, reason = "ANALYSIS", "compile-only, not materialized"
        elif model.materialized == "ephemeral":
            action, reason = "SKIP", "ephemeral (inlined as CTE)"
        else:
            model_hash = executor.compute_model_hash(name)
            stored_hash = state.get_hash(name)

            if full_refresh:
                action = "NEW" if stored_hash is None else "RUN"
                reason = "new model" if stored_hash is None else "--full-refresh"
            elif stored_hash is None:
                action, reason = "NEW", "never built"
            elif stored_hash == model_hash:
                action, reason = "SKIP", "up to date"
            else:
                action, reason = "RUN", "model changed"

        mat = model.materialized
        upstream = sorted(u for u in model.upstream if u in project.models)
        table_name = (f"{env}_" if env else "") + (model.alias or name)

        # Count affected downstream models (those not in current selection)
        all_downstream = dag.downstream_models(name)
        unselected_downstream = all_downstream - set(model_names)

        plan_rows.append({
            "name": name,
            "action": action,
            "materialized": mat,
            "table_name": table_name,
            "upstream": upstream,
            "reason": reason,
            "downstream_impact": len(unselected_downstream),
            "tags": model.tags,
            "hooks": len(model.pre_hook) + len(model.post_hook),
        })

    state.close()
    adapter.disconnect()

    if json_output:
        typer.echo(_json.dumps(plan_rows, indent=2))
        return

    counts: dict[str, int] = {}
    for r in plan_rows:
        counts[r["action"]] = counts.get(r["action"], 0) + 1

    env_label = f" [dim](env: {env})[/dim]" if env else ""
    var_label = f" [dim](vars: {', '.join(f'{k}={v}' for k,v in cli_vars.items())})[/dim]" if cli_vars else ""
    console.print(f"\n[bold]kelpmesh plan[/bold]  [dim]{project.path.name}[/dim]{env_label}{var_label}\n")

    table = Table(box=None, padding=(0, 1), show_header=True, header_style="bold dim")
    table.add_column("", width=2)         # icon
    table.add_column("action", width=9)
    table.add_column("model", style="cyan")
    table.add_column("type", style="dim", width=13)
    table.add_column("table", style="dim")
    table.add_column("upstream", style="dim")
    table.add_column("reason", style="dim italic")
    table.add_column("impact", style="dim", justify="right", width=7)

    for r in plan_rows:
        style = _ACTION_STYLE.get(r["action"], "")
        icon = _ACTION_ICON.get(r["action"], "·")
        ups = ", ".join(r["upstream"]) if r["upstream"] else "—"
        impact = f"+{r['downstream_impact']}" if r["downstream_impact"] else ""
        hook_note = f" [{r['hooks']}h]" if r["hooks"] else ""
        tag_note = f" [{','.join(r['tags'])}]" if r["tags"] else ""
        table.add_row(
            Text(icon, style=style),
            Text(r["action"], style=style),
            r["name"] + tag_note,
            r["materialized"] + hook_note,
            r["table_name"],
            ups,
            r["reason"],
            impact,
        )

    console.print(table)
    console.print()

    parts = []
    if counts.get("NEW"):
        parts.append(f"[cyan]{counts['NEW']} new[/cyan]")
    if counts.get("RUN"):
        parts.append(f"[green]{counts['RUN']} to run[/green]")
    if counts.get("SKIP"):
        parts.append(f"[dim]{counts['SKIP']} to skip[/dim]")
    if counts.get("DISABLED"):
        parts.append(f"[dim red]{counts['DISABLED']} disabled[/dim red]")
    if counts.get("ANALYSIS"):
        parts.append(f"[dim]{counts['ANALYSIS']} analyses[/dim]")

    total_impact = sum(r["downstream_impact"] for r in plan_rows if r["action"] in ("RUN", "NEW"))
    if total_impact:
        parts.append(f"[yellow]~{total_impact} downstream affected[/yellow]")

    console.print("  " + " · ".join(parts) if parts else "  [dim]Nothing to do.[/dim]")
    console.print()
    console.print("  [dim]Run [bold]kelpmesh run[/bold] to execute.[/dim]\n")
