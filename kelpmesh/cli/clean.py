import shutil
import time
from pathlib import Path

import typer
from rich.console import Console

from kelpmesh.state.engine import StateEngine

console = Console()


def _rmtree_onerror(func, path, exc_info):
    import os
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)


def clean_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """Remove compiled artifacts, cached files, and temporary output directories.

    Examples:

        kelpmesh clean

        kelpmesh clean --project-dir /path/to/project
    """
    project_path = project_dir.resolve()

    # On Windows, a previous kelpmesh process may briefly hold the DuckDB state
    # file lock. Retry a few times with a short sleep before giving up.
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            state = StateEngine(project_path)
            state.reset()
            state.close()
            last_err = None
            break
        except Exception as e:
            last_err = e
            time.sleep(0.4)
    if last_err is not None:
        console.print(
            f"[yellow]Could not reset state DB (file may be locked): {last_err}[/yellow]\n"
            "Continuing with artifact cleanup."
        )

    target_dir = project_path / "target"
    if target_dir.exists():
        shutil.rmtree(target_dir, onerror=_rmtree_onerror)

    console.print("[green]Project cleaned.[/green]")
