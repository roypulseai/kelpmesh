"""KelpMesh Prefect integration — tasks, flows, and blocks.

Installation:
    pip install kelpmesh[prefect]

Usage:

    from kelpmesh_prefect import KelpMeshBlock, kelpmesh_run_flow

    # Register the block once:
    block = KelpMeshBlock(project_dir="/data/my_project")
    block.save("my-project")

    # Use in a flow:
    @flow
    def daily_refresh():
        kelpmesh_run(project_dir="/data/my_project", tag="daily")
        kelpmesh_test(project_dir="/data/my_project")

    # Or with a deployment schedule:
    if __name__ == "__main__":
        daily_refresh.serve(cron="0 6 * * *")
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _prefect():
    try:
        import prefect
        return prefect
    except ImportError:
        raise ImportError(
            "Prefect is not installed. Run: pip install kelpmesh[prefect]"
        )


# ── KelpMesh Prefect Block ────────────────────────────────────────────────── #

class KelpMeshBlock:
    """Prefect Block that stores connection info for a KelpMesh project.

    Blocks are registered in the Prefect UI and can be shared across flows.
    """

    def __init__(self, project_dir: str = ".", python_path: str | None = None) -> None:
        self.project_dir = Path(project_dir)
        self.python = python_path or sys.executable

    def save(self, name: str) -> None:
        """Register this block in Prefect Cloud/Server under *name*."""
        try:
            prefect = _prefect()
            from prefect.blocks.core import Block

            class _Block(Block):
                _block_type_name = "kelpmesh"
                project_dir: str = str(self.project_dir)
                python_path: str = self.python

            _Block(
                project_dir=str(self.project_dir),
                python_path=self.python,
            ).save(name, overwrite=True)
        except Exception as exc:
            print(f"[kelpmesh_prefect] Block save failed: {exc}")

    def _run_cmd(self, *args: str, timeout: int = 7200) -> str:
        cmd = [self.python, "-m", "kelpmesh"] + list(args)
        result = subprocess.run(
            cmd, cwd=str(self.project_dir), capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"kelpmesh {args[0]} failed (rc={result.returncode}):\n{result.stderr}"
            )
        return result.stdout


# ── Prefect tasks ─────────────────────────────────────────────────────────── #

def kelpmesh_run(
    project_dir: str = ".",
    select: str | None = None,
    tag: str | None = None,
    full_refresh: bool = False,
    vars: dict | None = None,
) -> str:
    """Prefect task: run kelpmesh models."""
    prefect = _prefect()

    @prefect.task(name="kelpmesh-run", retries=1, retry_delay_seconds=30)
    def _task():
        block = KelpMeshBlock(project_dir=project_dir)
        args = ["run"]
        if select:
            args += ["--select", select]
        if tag:
            args += ["--tag", tag]
        if full_refresh:
            args.append("--full-refresh")
        if vars:
            for k, v in (vars or {}).items():
                args += ["--var", f"{k}={v}"]
        return block._run_cmd(*args)

    return _task()


def kelpmesh_test(project_dir: str = ".", select: str | None = None) -> str:
    """Prefect task: run kelpmesh tests."""
    prefect = _prefect()

    @prefect.task(name="kelpmesh-test")
    def _task():
        block = KelpMeshBlock(project_dir=project_dir)
        args = ["test"]
        if select:
            args += ["--select", select]
        return block._run_cmd(*args)

    return _task()


def kelpmesh_seed(project_dir: str = ".") -> str:
    """Prefect task: load seeds."""
    prefect = _prefect()

    @prefect.task(name="kelpmesh-seed")
    def _task():
        return KelpMeshBlock(project_dir=project_dir)._run_cmd("seed")

    return _task()


def kelpmesh_snapshot(project_dir: str = ".") -> str:
    """Prefect task: run snapshots."""
    prefect = _prefect()

    @prefect.task(name="kelpmesh-snapshot")
    def _task():
        return KelpMeshBlock(project_dir=project_dir)._run_cmd("snapshot")

    return _task()


# ── Pre-built flows ───────────────────────────────────────────────────────── #

def build_standard_flow(project_dir: str = ".", name: str = "kelpmesh-daily"):
    """Return a ready-made Prefect flow: seed → run → test → snapshot."""
    prefect = _prefect()

    @prefect.flow(name=name)
    def _flow(tag: str | None = None, full_refresh: bool = False):
        kelpmesh_seed(project_dir=project_dir)
        kelpmesh_run(project_dir=project_dir, tag=tag, full_refresh=full_refresh)
        kelpmesh_test(project_dir=project_dir)
        kelpmesh_snapshot(project_dir=project_dir)

    return _flow
