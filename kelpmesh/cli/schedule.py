"""kelpmesh schedule — built-in cron scheduler CLI.

Commands:
    kelpmesh schedule start     Start the scheduler (foreground by default)
    kelpmesh schedule start -d  Run as background daemon
    kelpmesh schedule stop      Stop a running daemon
    kelpmesh schedule list      Show all schedules and next run times
    kelpmesh schedule run <name> Fire a named schedule immediately

Example kelpmesh.yml:

    schedules:
      - name: daily_models
        cron: "0 6 * * *"
        command: run
        args: ["--tag", "daily"]

      - name: hourly_metrics
        interval: "every 1h"
        command: run
        args: ["--select", "metrics"]
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

console = Console()

schedule_app = typer.Typer(
    name="schedule",
    help="Built-in cron scheduler — run kelpmesh on a schedule without Airflow",
    no_args_is_help=True,
)

_PID_FILE = Path(".kelpmesh_scheduler.pid")


@schedule_app.command("start")
def start_cmd(
    project_dir: Path = typer.Option(Path("."), "--project-dir", "-p", help="Project root"),
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run as background daemon"),
) -> None:
    """Start the KelpMesh scheduler."""
    from kelpmesh.core.scheduler import KelpMeshScheduler, load_schedules_from_project

    schedules = load_schedules_from_project(project_dir.resolve())
    if not schedules:
        console.print(
            "[yellow]No schedules found.[/yellow] Add a 'schedules:' block to kelpmesh.yml."
        )
        raise typer.Exit(1)

    if daemon:
        _start_daemon(project_dir)
        return

    console.print(f"[bold cyan]KelpMesh Scheduler[/bold cyan] — {len(schedules)} schedule(s)")
    _show_schedule_table(schedules)
    console.print("\n[dim]Press Ctrl+C to stop.[/dim]\n")

    sched = KelpMeshScheduler(schedules, project_dir.resolve())
    sched.start()
    sched.wait()


@schedule_app.command("stop")
def stop_cmd() -> None:
    """Stop a running background daemon."""
    if not _PID_FILE.exists():
        console.print("[yellow]No running scheduler found.[/yellow]")
        raise typer.Exit(1)
    try:
        pid = int(_PID_FILE.read_text())
        os.kill(pid, signal.SIGTERM)
        _PID_FILE.unlink(missing_ok=True)
        console.print(f"[green]Stopped scheduler (pid {pid})[/green]")
    except ProcessLookupError:
        console.print("[yellow]Scheduler process not found (already stopped?).[/yellow]")
        _PID_FILE.unlink(missing_ok=True)
    except Exception as exc:
        console.print(f"[red]Error stopping scheduler: {exc}[/red]")
        raise typer.Exit(1)


@schedule_app.command("list")
def list_cmd(
    project_dir: Path = typer.Option(Path("."), "--project-dir", "-p"),
) -> None:
    """Show all schedules and their next run times."""
    from kelpmesh.core.scheduler import KelpMeshScheduler, load_schedules_from_project

    schedules = load_schedules_from_project(project_dir.resolve())
    if not schedules:
        console.print("[yellow]No schedules configured.[/yellow]")
        return

    sched = KelpMeshScheduler(schedules, project_dir.resolve())
    rows = sched.next_runs()

    tbl = Table(show_header=True, header_style="bold cyan")
    tbl.add_column("Name", style="bold")
    tbl.add_column("Schedule")
    tbl.add_column("Next run (UTC)", style="green")
    tbl.add_column("Command")

    for r in rows:
        tbl.add_row(r["name"], r["schedule"], r["next_run"], r["command"])

    console.print(tbl)


@schedule_app.command("run")
def run_now_cmd(
    name: str = typer.Argument(..., help="Schedule name to fire immediately"),
    project_dir: Path = typer.Option(Path("."), "--project-dir", "-p"),
) -> None:
    """Fire a named schedule immediately (ignore timing)."""
    from kelpmesh.core.scheduler import KelpMeshScheduler, load_schedules_from_project

    schedules = load_schedules_from_project(project_dir.resolve())
    match = [s for s in schedules if s.name == name]
    if not match:
        names = [s.name for s in schedules]
        console.print(f"[red]No schedule named '{name}'.[/red] Available: {names}")
        raise typer.Exit(1)

    sched = KelpMeshScheduler(schedules, project_dir.resolve())
    console.print(f"[cyan]Firing schedule:[/cyan] {name}")
    sched._fire(match[0])


def _show_schedule_table(schedules) -> None:
    from pathlib import Path

    from kelpmesh.core.scheduler import KelpMeshScheduler
    sched = KelpMeshScheduler(schedules, Path("."))
    rows = sched.next_runs()
    tbl = Table(show_header=True, header_style="bold cyan")
    tbl.add_column("Name", style="bold")
    tbl.add_column("Schedule")
    tbl.add_column("Next run (UTC)", style="green")
    tbl.add_column("Command")
    for r in rows:
        tbl.add_row(r["name"], r["schedule"], r["next_run"], r["command"])
    console.print(tbl)


def _start_daemon(project_dir: Path) -> None:
    """Fork to background and write PID file (POSIX only)."""
    if sys.platform == "win32":
        console.print(
            "[yellow]Background daemon mode is not supported on Windows.[/yellow]\n"
            "Run without --daemon flag, or use Task Scheduler / NSSM to run in background."
        )
        raise typer.Exit(1)
    pid = os.fork()
    if pid > 0:
        _PID_FILE.write_text(str(pid))
        console.print(f"[green]Scheduler daemon started (pid {pid})[/green]")
        console.print("[dim]Logs: logs/scheduler.log  |  Stop: kelpmesh schedule stop[/dim]")
        return
    # child
    os.setsid()
    from kelpmesh.core.scheduler import KelpMeshScheduler, load_schedules_from_project
    schedules = load_schedules_from_project(project_dir.resolve())
    daemon_sched = KelpMeshScheduler(schedules, project_dir.resolve())
    daemon_sched.start()
    daemon_sched.wait()
    sys.exit(0)
