import os
import sys
import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from briq.core.project import Project
from briq.state.engine import StateEngine
from briq.adapters import get_adapter
from briq.core.errors import sanitize_exception_message
from briq.core.crypto import _FERNET_AVAILABLE

console = Console()

TELEMETRY_BLOCKLIST = [
    "posthog", "sentry_sdk", "datadog", "statsd", "telemetry",
    "analytics", "segment", "amplitude", "mixpanel",
]


def debug_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    project_path = project_dir.resolve()

    config_file = project_path / "briq.yml"
    console.print(Panel(f"[bold]briq debug[/bold] - {project_path}", expand=False))

    if config_file.exists():
        console.print(f"[green]Config file:[/green] {config_file}")
    else:
        console.print("[yellow]Config file:[/yellow] Not found (using defaults)")

    project = Project(project_path)
    console.print(f"[bold]Models:[/bold] {len(project.models)}")
    for name in sorted(project.models.keys()):
        model = project.models[name]
        console.print(f"  [cyan]{name}[/cyan] ({model.materialized})")

    state = StateEngine(project_path)
    states = state.get_all_states()
    console.print(f"[bold]State entries:[/bold] {len(states)}")
    for s in states:
        console.print(f"  [cyan]{s['model_name']}[/cyan] hash={s['hash']} rows={s['row_count']}")
    state.close()

    adapter = get_adapter(project.config.warehouse, project_path=str(project_path))
    try:
        adapter.connect()
        console.print("[green]Warehouse connection: OK[/green]")
        adapter.disconnect()
    except Exception as e:
        console.print(f"[red]Warehouse connection: FAILED ({sanitize_exception_message(str(e))})[/red]")

    console.print(f"[bold]Warehouse type:[/bold] {project.config.warehouse.type}")
    console.print(f"[bold]Test path:[/bold] {project_path / project.config.tests_path}")
    console.print(f"[bold]Target path:[/bold] {project_path / project.config.target_path}")

    console.print(Panel("[bold]Security[/bold]", expand=False))
    enc_key = os.environ.get("BRIQ_ENCRYPTION_KEY")
    if enc_key:
        masked = enc_key[:8] + "..." + enc_key[-4:] if len(enc_key) > 12 else "(set)"
        console.print(f"[green]Encryption key:[/green] {masked}")
    else:
        console.print("[yellow]Encryption key:[/yellow] Not set (set BRIQ_ENCRYPTION_KEY)")
    console.print(f"[bold]Cryptography available:[/bold] {'Yes' if _FERNET_AVAILABLE else 'No'}")

    loaded_telemetry = [p for p in TELEMETRY_BLOCKLIST if p in sys.modules]
    if loaded_telemetry:
        console.print(f"[red]Telemetry packages loaded:[/red] {', '.join(loaded_telemetry)}")
    else:
        console.print("[green]Telemetry guard:[/green] No telemetry packages detected")
