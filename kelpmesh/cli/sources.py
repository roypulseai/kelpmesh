"""kelpmesh source commands — freshness checking."""

import re
from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kelpmesh.adapters import get_adapter
from kelpmesh.core.project import Project
from kelpmesh.state.engine import StateEngine

source_app = typer.Typer(help="Source definitions and freshness — subcommands: list, freshness")
console = Console()


def _parse_duration(dur: str) -> timedelta:
    """Parse a duration string like '24h', '72h', '30m'."""
    m = re.match(r"^(\d+)\s*(h|hour|hours|m|min|minutes?|d|day|days)?$", dur.strip().lower())
    if not m:
        return timedelta(hours=24)
    val = int(m.group(1))
    unit = m.group(2) or "h"
    if unit.startswith("d"):
        return timedelta(days=val)
    if unit.startswith("m"):
        return timedelta(minutes=val)
    return timedelta(hours=val)


@source_app.command(name="freshness")
def source_freshness_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """Check source freshness against configured thresholds."""
    project_path = project_dir.resolve()
    project = Project(project_path)

    if not project.sources:
        console.print("[yellow]No sources defined in sources.yml[/yellow]")
        return

    adapter = get_adapter(project.config.warehouse, project_path=str(project_path))
    state = StateEngine(project.path)
    adapter.connect()

    table_disp = Table(title="Source Freshness")
    table_disp.add_column("Source")
    table_disp.add_column("Table")
    table_disp.add_column("Max Loaded At")
    table_disp.add_column("Status")
    table_disp.add_column("Warn After")
    table_disp.add_column("Error After")

    now = datetime.now()

    for src in project.sources.values():
        table_ref = src.table
        if src.schema_name:
            table_ref = f"{src.schema_name}.{table_ref}"
        if src.database:
            table_ref = f"{src.database}.{table_ref}"

        try:
            result = adapter.execute(
                f"SELECT MAX({src.loaded_at_field}) AS max_ts FROM {table_ref}"
            )
            max_ts = result[0]["max_ts"] if result and result[0]["max_ts"] else None
        except Exception:
            max_ts = None
            status = "error"
            state.record_freshness(src.name, None, "error")

        if max_ts is not None:
            if isinstance(max_ts, str):
                max_dt = datetime.fromisoformat(max_ts)
            else:
                max_dt = max_ts
            age = now - max_dt

            status = "pass"
            if src.freshness:
                warn = _parse_duration(src.freshness.warn_after)
                error = _parse_duration(src.freshness.error_after)
                if age > error:
                    status = "error"
                elif age > warn:
                    status = "warn"
            state.record_freshness(src.name, max_dt, status)
        else:
            status = "error"
            state.record_freshness(src.name, None, "error")

        warn_str = src.freshness.warn_after if src.freshness else "—"
        error_str = src.freshness.error_after if src.freshness else "—"
        max_str = max_ts.isoformat()[:19] if isinstance(max_ts, datetime) else (str(max_ts) if max_ts else "—")

        status_icon = {
            "pass": "[green]✓ PASS[/green]",
            "warn": "[yellow]⚠ WARN[/yellow]",
            "error": "[red]✗ ERROR[/red]",
        }.get(status, "[dim]unchecked[/dim]")

        table_disp.add_row(src.name, src.table, max_str, status_icon, warn_str, error_str)

    console.print(table_disp)
    adapter.disconnect()
    state.close()


@source_app.command(name="list")
def source_list_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """List all defined sources."""
    project_path = project_dir.resolve()
    project = Project(project_path)

    if not project.sources:
        console.print("[yellow]No sources defined in sources.yml[/yellow]")
        return

    table_disp = Table(title="Sources")
    table_disp.add_column("Name")
    table_disp.add_column("Table")
    table_disp.add_column("Loader")
    table_disp.add_column("Freshness")
    table_disp.add_column("Description")

    for src in project.sources.values():
        fresh = f"warn={src.freshness.warn_after}, error={src.freshness.error_after}" if src.freshness else "—"
        table_disp.add_row(src.name, src.table, src.loader, fresh, src.description or "")

    console.print(table_disp)
