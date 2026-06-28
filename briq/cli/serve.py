"""briq serve — REST API for the semantic layer (metrics query endpoint)."""

from __future__ import annotations
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()


def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(7788, "--port", "-p", help="Bind port"),
    project_dir: Path = typer.Option(Path("."), "--project-dir", help="briq project root"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on file changes"),
):
    """Start a local REST API server exposing metrics from the semantic layer."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn is required: pip install uvicorn[/red]")
        raise typer.Exit(1)

    from briq.semantic.serve import create_serve_app

    proj = project_dir.resolve()
    app = create_serve_app(proj)

    console.print(f"[green]briq serve[/green] listening on [bold]http://{host}:{port}[/bold]")
    console.print(f"  Project: {proj}")
    console.print(f"  Docs:    http://{host}:{port}/docs")

    uvicorn.run(app, host=host, port=port, reload=reload)
