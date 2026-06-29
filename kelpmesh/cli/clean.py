import typer
import shutil
from pathlib import Path
from rich.console import Console
from kelpmesh.state.engine import StateEngine

console = Console()


def _rmtree_onerror(func, path, exc_info):
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)


def clean_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """Remove compiled artifacts, cached files, and temporary output directories."""
    import os
    project_path = project_dir.resolve()

    state = StateEngine(project_path)
    state.reset()
    state.close()

    target_dir = project_path / "target"
    if target_dir.exists():
        shutil.rmtree(target_dir, onerror=_rmtree_onerror)

    console.print("[green]Project cleaned.[/green]")
