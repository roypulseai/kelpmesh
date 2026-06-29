"""kelpmesh debug — validate project config, connection, and environment."""

from __future__ import annotations

import os
import sys
import typer
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from kelpmesh.core.errors import sanitize_exception_message
from kelpmesh.core.crypto import _FERNET_AVAILABLE

console = Console()

TELEMETRY_BLOCKLIST = [
    "posthog", "sentry_sdk", "datadog", "statsd", "telemetry",
    "analytics", "segment", "amplitude", "mixpanel",
]

_FIELD_HINTS: dict[str, dict[str, str]] = {
    "postgres": {
        "host": "Set 'host' in kelpmesh.yml warehouse config",
        "user": "Set 'user' in kelpmesh.yml warehouse config",
        "password": "Set 'password' (or use KELPMESH_PG_PASSWORD env var)",
        "database": "Set 'database' in kelpmesh.yml warehouse config",
    },
    "redshift": {
        "host": "Set 'host' to your Redshift cluster endpoint",
        "user": "Set 'user' in kelpmesh.yml warehouse config",
        "password": "Set 'password' (or use KELPMESH_RS_PASSWORD env var)",
        "database": "Set 'database' in kelpmesh.yml warehouse config",
    },
    "snowflake": {
        "account": "Set 'account' to your Snowflake account identifier (e.g. xy12345.us-east-1)",
        "user": "Set 'user' in kelpmesh.yml warehouse config",
        "password": "Set 'password' (or use KELPMESH_SF_PASSWORD env var)",
    },
    "bigquery": {
        "project_id": "Set 'project_id' to your GCP project ID",
        "private_key_path": "Set 'private_key_path' to your service account JSON, or use ADC (gcloud auth)",
    },
    "databricks": {
        "account": "Set 'account' to your Databricks server hostname",
        "path": "Set 'path' to your SQL warehouse HTTP path",
        "password": "Set 'password' to your personal access token",
    },
    "fabric": {
        "account": "Set 'account' to your Fabric SQL Analytics endpoint hostname",
        "database": "Set 'database' in kelpmesh.yml warehouse config",
    },
}


def _check_config(config) -> list[tuple[str, str, str]]:
    """Return list of (field, status, hint) tuples for all relevant config fields."""
    rows = []
    wh = config.warehouse
    rows.append(("warehouse.type", "ok", wh.type))
    hints = _FIELD_HINTS.get(wh.type, {})

    check_fields = {
        "postgres": ["host", "port", "user", "password", "database"],
        "redshift": ["host", "user", "password", "database"],
        "snowflake": ["account", "user", "password"],
        "bigquery": ["project_id", "private_key_path"],
        "databricks": ["account", "path", "password"],
        "fabric": ["account", "database"],
        "duckdb": ["path"],
    }.get(wh.type, [])

    for field in check_fields:
        val = getattr(wh, field, None)
        if val:
            display = "****" if field in ("password",) else str(val)
            rows.append((f"warehouse.{field}", "ok", display))
        else:
            hint = hints.get(field, f"Set '{field}' in kelpmesh.yml")
            rows.append((f"warehouse.{field}", "missing", hint))
    return rows


def debug_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    connection: bool = typer.Option(True, "--connection/--no-connection", help="Test warehouse connection"),
):
    """Validate project config, warehouse connection, and environment.

    Checks kelpmesh.yml fields, tests the warehouse connection, reports
    model count, state, encryption, and telemetry guard status.

    Examples:
        kelpmesh debug
        kelpmesh debug --no-connection   # skip live connection test
    """
    from kelpmesh.core.project import Project
    from kelpmesh.state.engine import StateEngine
    from kelpmesh.adapters import get_adapter

    project_path = project_dir.resolve()
    config_file = project_path / "kelpmesh.yml"

    console.print()
    console.print(Panel(f"[bold]kelpmesh debug[/bold]  [dim]{project_path}[/dim]", expand=False))
    console.print()

    # ── Config file ──────────────────────────────────────────────────────────
    if config_file.exists():
        console.print(f"  [green]✓[/green]  config file        {config_file}")
    else:
        console.print(f"  [yellow]⚠[/yellow]  config file        Not found — using defaults")

    try:
        from kelpmesh.core.config import ProjectConfig
        config = ProjectConfig.load(project_path)
        console.print(f"  [green]✓[/green]  project name       {config.name}")
    except Exception as e:
        console.print(f"  [red]✗[/red]  config parse       {sanitize_exception_message(str(e))}")
        console.print("\n  [red]Fix kelpmesh.yml before proceeding.[/red]\n")
        raise typer.Exit(1)

    # ── Warehouse config field check ─────────────────────────────────────────
    console.print()
    field_table = Table(box=None, padding=(0, 2), show_header=False)
    field_table.add_column("icon", width=4)
    field_table.add_column("field", style="dim", width=26)
    field_table.add_column("value")

    all_ok = True
    for field, status, detail in _check_config(config):
        if status == "ok":
            field_table.add_row("[green]✓[/green]", field, f"[dim]{detail}[/dim]")
        else:
            field_table.add_row("[red]✗[/red]", field, f"[red]MISSING[/red]  [dim]{detail}[/dim]")
            all_ok = False
    console.print(field_table)

    if not all_ok:
        console.print(
            "\n  [yellow]Fix missing fields in kelpmesh.yml before running.[/yellow]\n"
            "  Example kelpmesh.yml:\n"
            "  [dim]warehouse:\n"
            "    type: postgres\n"
            "    host: localhost\n"
            "    user: myuser\n"
            "    password: mypass\n"
            "    database: mydb[/dim]"
        )

    # ── Live connection test ─────────────────────────────────────────────────
    if connection:
        console.print()
        adapter = get_adapter(config.warehouse, project_path=str(project_path))
        try:
            adapter.connect()
            console.print(f"  [green]✓[/green]  warehouse          Connected to {config.warehouse.type}")
            adapter.disconnect()
        except Exception as e:
            msg = str(e)
            console.print(f"  [red]✗[/red]  warehouse          Connection failed")

            # Actionable hints for the most common errors
            msg_lower = msg.lower()
            if "password authentication failed" in msg_lower or "authentication failed" in msg_lower:
                console.print("          [dim]→ Check 'password' in kelpmesh.yml (wrong credentials)[/dim]")
            elif "could not connect" in msg_lower or "connection refused" in msg_lower:
                console.print("          [dim]→ Check 'host' and 'port' — server may not be reachable[/dim]")
            elif "does not exist" in msg_lower and "database" in msg_lower:
                console.print("          [dim]→ Check 'database' — database does not exist on this server[/dim]")
            elif "timeout" in msg_lower:
                console.print("          [dim]→ Connection timed out — check firewall / VPN / network[/dim]")
            elif "ssl" in msg_lower:
                console.print("          [dim]→ SSL error — try adding sslmode: require to kelpmesh.yml[/dim]")
            elif "no module named" in msg_lower:
                pkg = msg.split("'")[1] if "'" in msg else "driver"
                console.print(f"          [dim]→ Missing driver: pip install {pkg}[/dim]")
            else:
                console.print(f"          [dim]→ {sanitize_exception_message(msg[:120])}[/dim]")
    else:
        console.print("\n  [dim]Connection test skipped (--no-connection)[/dim]")

    # ── Project models ───────────────────────────────────────────────────────
    console.print()
    try:
        project = Project(project_path)
        models = project.models
        console.print(f"  [green]✓[/green]  models             {len(models)} found")

        mat_counts: dict[str, int] = {}
        for m in models.values():
            mat_counts[m.materialized] = mat_counts.get(m.materialized, 0) + 1
        for mat, count in sorted(mat_counts.items()):
            console.print(f"             [dim]{mat:<14} {count}[/dim]")

        if project.macro_loader.has_macros:
            console.print(f"  [green]✓[/green]  macros             loaded from {config.macros_path}/")
        else:
            console.print(f"  [dim]·[/dim]  macros             none (create macros/*.sql to add)")
    except Exception as e:
        console.print(f"  [red]✗[/red]  project load       {sanitize_exception_message(str(e))}")

    # ── State ────────────────────────────────────────────────────────────────
    try:
        state = StateEngine(project_path)
        states = state.get_all_states()
        console.print(f"  [green]✓[/green]  state              {len(states)} model(s) in state")
        state.close()
    except Exception as e:
        console.print(f"  [yellow]⚠[/yellow]  state              {sanitize_exception_message(str(e))}")

    # ── Security ─────────────────────────────────────────────────────────────
    console.print()
    enc_key = os.environ.get("KELPMESH_ENCRYPTION_KEY")
    if enc_key:
        masked = enc_key[:8] + "…" + enc_key[-4:] if len(enc_key) > 12 else "(set)"
        console.print(f"  [green]✓[/green]  encryption key     {masked}")
    else:
        console.print("  [dim]·[/dim]  encryption key     Not set (export KELPMESH_ENCRYPTION_KEY=<key>)")
    console.print(f"  {'[green]✓[/green]' if _FERNET_AVAILABLE else '[yellow]⚠[/yellow]'}  cryptography       {'available' if _FERNET_AVAILABLE else 'not installed (pip install cryptography)'}")

    loaded_telemetry = [p for p in TELEMETRY_BLOCKLIST if p in sys.modules]
    if loaded_telemetry:
        console.print(f"  [red]✗[/red]  telemetry guard    BLOCKED packages detected: {', '.join(loaded_telemetry)}")
    else:
        console.print("  [green]✓[/green]  telemetry guard    Clean — no telemetry packages loaded")

    # ── Python / kelpmesh version ────────────────────────────────────────────────
    console.print()
    try:
        from importlib.metadata import version
        km_ver = version("kelpmesh")
    except Exception:
        km_ver = "dev"
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    console.print(f"  [dim]kelpmesh {km_ver} · Python {py_ver} · {sys.platform}[/dim]")
    console.print()
