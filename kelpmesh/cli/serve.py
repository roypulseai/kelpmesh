"""kelpmesh serve — REST API for the semantic layer (metrics query endpoint)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

console = Console()


def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(7788, "--port", "-p", help="Bind port"),
    project_dir: Path = typer.Option(Path("."), "--project-dir", help="kelpmesh project root"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on file changes"),
):
    """Start a local REST API server exposing metrics from the semantic layer.

    Examples:

        kelpmesh serve

        kelpmesh serve --port 9000

        kelpmesh serve --host 0.0.0.0
    """
    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn is required: pip install uvicorn[/red]")
        raise typer.Exit(1)

    from kelpmesh.semantic.serve import create_serve_app

    proj = project_dir.resolve()
    app = create_serve_app(proj)

    console.print(f"[green]kelpmesh serve[/green] listening on [bold]http://{host}:{port}[/bold]")
    console.print(f"  Project: {proj}")
    console.print(f"  Docs:    http://{host}:{port}/docs")

    uvicorn.run(app, host=host, port=port, reload=reload)
