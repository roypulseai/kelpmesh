import json
import os
import typer
from pathlib import Path
import webbrowser
from rich.console import Console
from kelpmesh.core.project import Project
from kelpmesh.docs.generator import DocsGenerator

console = Console()


def docs_cmd(
    serve: bool = typer.Option(
        False, "--serve", "-s", help="Serve docs with a local HTTP server"
    ),
    open_browser: bool = typer.Option(
        True, "--open", "-o", help="Open browser after serving"
    ),
    port: int = typer.Option(8000, "--port", help="Port for HTTP server"),
    project_dir: Path = typer.Option(
        ".", "--project-dir", "-p", help="Project directory"
    ),
):
    project = Project(project_dir.resolve())
    generator = DocsGenerator(project)

    output_dir = project.path / "target" / "docs"
    index_path = generator.generate(output_dir)

    console.print(f"[green]Documentation generated:[/green] {index_path}")

    if serve:
        import http.server
        import socketserver
        import threading

        class DocsHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(output_dir), **kwargs)
        handler = DocsHandler
        server = socketserver.TCPServer(("", port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        url = f"http://localhost:{port}"
        console.print(f"[green]Serving docs at:[/green] {url}")

        if open_browser:
            webbrowser.open(url)

        console.print("[dim]Press Ctrl+C to stop serving[/dim]")
        try:
            thread.join()
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping server...[/yellow]")
            server.shutdown()


def manifest_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    project = Project(project_dir.resolve())
    generator = DocsGenerator(project)
    output_dir = project.path / "target" / "docs"
    generator.generate(output_dir)
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        print(manifest_path.read_text(encoding="utf-8"))
    else:
        print(json.dumps({"models": []}))
