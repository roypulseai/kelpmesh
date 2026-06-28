"""kelpmesh studio — launch the bundled kelpmesh Studio web dashboard."""

from __future__ import annotations

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()


def studio_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8765, "--port", "-p", help="Port to listen on"),
    project_dir: Path = typer.Option(".", "--project-dir", help="Project directory"),
    debug: bool = typer.Option(False, "--debug", help="Enable auto-reload"),
):
    """Launch kelpmesh Studio — the browser-based SQL IDE and DAG dashboard.

    Opens a local web server with the kelpmesh Studio UI at http://localhost:<port>.
    Requires: pip install kelpmesh[studio]

    Examples:
        kelpmesh studio
        kelpmesh studio --port 9000
        kelpmesh studio --project-dir /path/to/project
    """
    try:
        import uvicorn
    except ImportError:
        console.print(
            "\n  [red]uvicorn not installed.[/red]\n"
            "  Install with: [bold]pip install kelpmesh\\[studio][/bold]\n"
        )
        raise typer.Exit(1)

    try:
        import fastapi  # noqa: F401
    except ImportError:
        console.print(
            "\n  [red]fastapi not installed.[/red]\n"
            "  Install with: [bold]pip install kelpmesh\\[studio][/bold]\n"
        )
        raise typer.Exit(1)

    from kelpmesh.studio.app import create_app

    project_path = str(project_dir.resolve())
    app = create_app(project_path)

    url = f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}"
    console.print()
    console.print(f"  [bold cyan]kelpmesh Studio[/bold cyan]  [dim]Pure SQL Transformation IDE[/dim]")
    console.print(f"  Open: [bold]{url}[/bold]")
    console.print(f"  Project: [dim]{project_path}[/dim]")
    console.print(f"  Press [bold]Ctrl+C[/bold] to stop.\n")

    try:
        import webbrowser
        import threading
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    except Exception:
        pass

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False,
        log_level="warning",
    )
