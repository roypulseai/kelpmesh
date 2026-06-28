"""briq freshness — check source table freshness against warn/error thresholds."""

from __future__ import annotations

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.text import Text
from datetime import datetime, timedelta

console = Console()


def freshness_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    select: Optional[str] = typer.Option(None, "--select", "-s", help="Filter to a specific source"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check whether source tables have been updated within their configured freshness thresholds.

    Reads ``sources:`` blocks from ``schema.yml`` files. Each source table can
    declare::

        freshness:
          warn_after: {count: 12, period: hour}
          error_after: {count: 24, period: hour}
        loaded_at_field: updated_at

    Sources without ``freshness:`` configuration are skipped.

    Example:
        briq freshness
        briq freshness --select raw.orders
    """
    import json as _json
    from briq.core.project import Project
    from briq.adapters import get_adapter
    from briq.state.engine import StateEngine

    project = Project(project_dir.resolve())
    adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
    state = StateEngine(project.path)

    results = []
    for src_key, src in project.sources.items():
        if select and src_key != select and src.name != select:
            continue

        freshn_cfg = getattr(src, "freshness", None) or {}
        loaded_at_field = getattr(src, "loaded_at_field", None)
        if not freshn_cfg or not loaded_at_field:
            continue

        warn_after = _parse_duration(freshn_cfg.get("warn_after", {}))
        error_after = _parse_duration(freshn_cfg.get("error_after", {}))

        try:
            rows = adapter.execute(
                f"SELECT MAX({loaded_at_field}) AS max_ts FROM {src_key.replace('.', '_')}"
            )
            max_ts = rows[0]["max_ts"] if rows else None
        except Exception:
            max_ts = None

        status, age_s = _evaluate_freshness(max_ts, warn_after, error_after)
        age_str = _fmt_age(age_s) if age_s is not None else "unknown"

        state.record_freshness(src_key, max_ts, status)

        results.append({
            "source": src_key,
            "loaded_at": max_ts.isoformat() if max_ts else None,
            "age": age_str,
            "status": status,
        })

    adapter.disconnect()
    state.close()

    if not results:
        console.print("[dim]No sources with freshness configuration found.[/dim]")
        return

    if json_output:
        typer.echo(_json.dumps(results, indent=2))
        return

    table = Table(box=None, padding=(0, 1), show_header=True, header_style="bold dim")
    table.add_column("source", style="cyan")
    table.add_column("last loaded", width=20)
    table.add_column("age", width=12)
    table.add_column("status", width=8)

    _st = {"pass": "green", "warn": "yellow", "error": "red", "unknown": "dim"}
    for r in results:
        table.add_row(
            r["source"],
            (r["loaded_at"] or "")[:19],
            r["age"],
            Text(r["status"], style=_st.get(r["status"], "")),
        )

    console.print(f"\n[bold]briq freshness[/bold]\n")
    console.print(table)
    console.print()

    errors = [r for r in results if r["status"] == "error"]
    if errors:
        raise typer.Exit(1)


def _parse_duration(cfg: dict) -> timedelta | None:
    if not cfg:
        return None
    count = cfg.get("count", 1)
    period = cfg.get("period", "hour").lower()
    if period in ("hour", "hours"):
        return timedelta(hours=count)
    if period in ("day", "days"):
        return timedelta(days=count)
    if period in ("minute", "minutes"):
        return timedelta(minutes=count)
    return timedelta(hours=count)


def _evaluate_freshness(
    max_ts,
    warn_after: timedelta | None,
    error_after: timedelta | None,
) -> tuple[str, float | None]:
    if max_ts is None:
        return "unknown", None

    now = datetime.now()
    if hasattr(max_ts, "replace"):
        max_ts = max_ts.replace(tzinfo=None)
    age = now - max_ts
    age_s = age.total_seconds()

    if error_after and age > error_after:
        return "error", age_s
    if warn_after and age > warn_after:
        return "warn", age_s
    return "pass", age_s


def _fmt_age(seconds: float) -> str:
    if seconds < 120:
        return f"{int(seconds)}s"
    if seconds < 7200:
        return f"{int(seconds / 60)}m"
    if seconds < 86400 * 2:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"
