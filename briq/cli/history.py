"""briq history — query historical run outcomes."""

from __future__ import annotations

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

_STATUS_STYLE = {
    "success": "green",
    "failed": "red",
    "skipped": "dim",
}


def history_cmd(
    model: Optional[str] = typer.Argument(None, help="Filter to a specific model"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of rows to show"),
    env: Optional[str] = typer.Option(None, "--env", "-e", help="Filter by environment"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show historical run outcomes for models.

    Displays the last N runs across all models (or a specific model),
    including status, row count, elapsed time, and environment.

    Example:
        briq history
        briq history orders --limit 10
        briq history --env prod
    """
    import json as _json
    from briq.observability.history import RunHistory

    project_path = project_dir.resolve()
    history = RunHistory(project_path)

    rows = history.get_history(model_name=model, limit=limit, env=env)
    history.close()

    if not rows:
        console.print("[dim]No run history found.[/dim]")
        return

    if json_output:
        typer.echo(_json.dumps(rows, indent=2))
        return

    table = Table(box=None, padding=(0, 1), show_header=True, header_style="bold dim")
    table.add_column("started", width=19, no_wrap=True)
    table.add_column("run_id", width=9, style="dim", no_wrap=True)
    table.add_column("model", style="cyan", no_wrap=True, min_width=12)
    table.add_column("status", width=9, no_wrap=True)
    table.add_column("rows", justify="right", width=8)
    table.add_column("elapsed", justify="right", width=8, style="dim")
    table.add_column("env", width=10, style="dim")

    for r in rows:
        status_style = _STATUS_STYLE.get(r["status"], "")
        table.add_row(
            (r["started_at"] or "")[:19],
            r["run_id"][:8] if r["run_id"] else "—",
            r["model_name"],
            Text(r["status"], style=status_style),
            str(r["row_count"]) if r["row_count"] is not None else "—",
            f"{r['elapsed_s']:.2f}s" if r["elapsed_s"] is not None else "—",
            r["env"] or "default",
        )

    label = f"  [dim]model: {model}[/dim]" if model else ""
    console.print(f"\n[bold]briq history[/bold]{label}\n")
    console.print(table)
    console.print()
