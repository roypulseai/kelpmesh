"""briq studio — launch the briq Studio web IDE."""

from __future__ import annotations

import typer
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


def studio_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8765, "--port", "-p", help="Port to listen on"),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Studio data directory"),
    debug: bool = typer.Option(False, "--debug", help="Enable auto-reload"),
):
    """Launch briq Studio — the browser-based SQL IDE.

    Opens a local web server with the briq Studio UI at http://localhost:<port>.
    Requires: pip install briq[studio]

    Example:
        briq studio
        briq studio --port 9000 --debug
    """
    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn not installed.[/red] Run: [bold]pip install briq[studio][/bold]")
        raise typer.Exit(1)

    try:
        import fastapi  # noqa: F401
    except ImportError:
        console.print("[red]fastapi not installed.[/red] Run: [bold]pip install briq[studio][/bold]")
        raise typer.Exit(1)

    import os
    if data_dir:
        os.environ["BRIQ_STUDIO_DATA"] = str(data_dir.resolve())
    if debug:
        os.environ["BRIQ_STUDIO_DEBUG"] = "1"
    os.environ["BRIQ_STUDIO_HOST"] = host
    os.environ["BRIQ_STUDIO_PORT"] = str(port)

    url = f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}"
    console.print(f"\n[bold cyan]briq Studio[/bold cyan]  [dim]Pure SQL Transformation IDE[/dim]")
    console.print(f"  Open: [bold]{url}[/bold]\n")

    uvicorn.run(
        "briq_studio.server:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info" if not debug else "debug",
    )
