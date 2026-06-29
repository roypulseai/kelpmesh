"""kelpmesh rollback — revert model state so the next run rebuilds from scratch.

Rollback does not restore data that was overwritten in the warehouse — it clears
the state-engine record so that `kelpmesh run` treats the model as if it has never
run and performs a full rebuild.  For incremental models the rebuild will be a
full refresh regardless of whether `--full-refresh` is passed.

Examples:
    kelpmesh rollback                   # preview what would be rolled back
    kelpmesh rollback --apply           # apply the rollback
    kelpmesh rollback orders customers  # only these models
    kelpmesh rollback --steps 2         # show last-2-runs history
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()


def rollback_cmd(
    models: list[str] = typer.Argument(None, help="Model names to roll back (default: all)"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    target: Optional[str] = typer.Option(None, "--target", help="Active profile"),
    env: Optional[str] = typer.Option(None, "--env", "-e", help="Environment prefix"),
    steps: int = typer.Option(1, "--steps", "-n", help="Show N previous run records"),
    apply: bool = typer.Option(False, "--apply", help="Actually clear state (default: dry-run preview)"),
):
    """Roll back model state — force the next run to rebuild.

    By default this is a dry-run: it shows what would be affected.
    Pass --apply to clear the state entries.

    NOTE: This marks models as 'needs rebuild'.  It does NOT restore previous
    data in the warehouse — for that you need a full re-run after rollback.
    """
    from kelpmesh.core.config import ProjectConfig
    from kelpmesh.state.engine import StateEngine

    project_path = project_dir.resolve()
    config = ProjectConfig.load(project_path, target=target)

    state = StateEngine(project_path)
    all_states = state.get_all_states()

    if not all_states:
        console.print("[yellow]No model state found. Nothing to roll back.[/yellow]")
        state.close()
        raise typer.Exit(0)

    # Filter to requested models
    if models:
        targets = [s for s in all_states if s["model_name"] in models]
        missing = set(models) - {s["model_name"] for s in targets}
        if missing:
            console.print(f"[yellow]Models not in state: {', '.join(sorted(missing))}[/yellow]")
    else:
        targets = all_states

    if not targets:
        console.print("[yellow]No matching models in state.[/yellow]")
        state.close()
        raise typer.Exit(0)

    mode_label = "[bold green]WILL ROLL BACK[/bold green]" if apply else "[dim]DRY RUN — pass --apply to execute[/dim]"
    console.print(f"\n[bold]kelpmesh rollback[/bold]  {mode_label}\n")

    table = Table(box=None, padding=(0, 2), show_header=True, header_style="dim")
    table.add_column("Model", style="cyan")
    table.add_column("Last Run", style="dim")
    table.add_column("Row Count", justify="right", style="dim")
    table.add_column("Hash (first 8)", style="dim")
    table.add_column("Action")

    for s in sorted(targets, key=lambda x: x["model_name"]):
        last_run = s.get("last_run_at") or "never"
        if last_run != "never" and "T" in last_run:
            last_run = last_run.replace("T", " ")[:19]
        row_count = str(s.get("row_count") or 0)
        hash_preview = (s.get("hash") or "")[:8]
        action = Text("clear state → rebuild", style="bold yellow") if apply else Text("would clear state", style="dim")
        table.add_row(s["model_name"], last_run, row_count, hash_preview, action)

    console.print(table)

    if apply:
        cleared = 0
        for s in targets:
            state.reset(s["model_name"])
            cleared += 1
        console.print(f"\n[green]✓[/green] Rolled back {cleared} model(s). Next [bold]kelpmesh run[/bold] will rebuild them.\n")
    else:
        console.print(
            f"\n[dim]{len(targets)} model(s) would be rolled back. "
            "Run with [bold]--apply[/bold] to proceed.[/dim]\n"
        )

    state.close()
