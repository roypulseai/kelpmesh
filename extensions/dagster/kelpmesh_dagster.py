"""KelpMesh Dagster integration — resources, assets, and ops.

Installation:
    pip install kelpmesh[dagster]

Usage in a Dagster repository:

    from kelpmesh_dagster import (
        KelpMeshResource,
        kelpmesh_run_op,
        kelpmesh_test_op,
        build_kelpmesh_assets,
    )

    defs = Definitions(
        assets=build_kelpmesh_assets(project_dir="/data/my_project", tags=["daily"]),
        resources={"kelpmesh": KelpMeshResource(project_dir="/data/my_project")},
    )
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any


# ── Lazy Dagster imports so the module is importable without dagster installed ──

def _dagster():
    try:
        import dagster
        return dagster
    except ImportError:
        raise ImportError(
            "Dagster is not installed. Run: pip install kelpmesh[dagster]"
        )


class KelpMeshResource:
    """Dagster ConfigurableResource wrapping the kelpmesh CLI.

    Example:

        @asset
        def my_models(kelpmesh: KelpMeshResource):
            kelpmesh.run(select="tag:daily")
    """

    def __init__(self, project_dir: str = ".", python_path: str | None = None) -> None:
        self.project_dir = Path(project_dir)
        self.python = python_path or sys.executable

    def _run_cmd(self, *args: str, timeout: int = 7200) -> subprocess.CompletedProcess:
        cmd = [self.python, "-m", "kelpmesh"] + list(args)
        result = subprocess.run(
            cmd,
            cwd=str(self.project_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"kelpmesh {args[0]} failed (rc={result.returncode}):\n{result.stderr}"
            )
        return result

    def run(self, select: str | None = None, tag: str | None = None,
            full_refresh: bool = False, vars: dict | None = None) -> str:
        args = ["run"]
        if select:
            args += ["--select", select]
        if tag:
            args += ["--tag", tag]
        if full_refresh:
            args.append("--full-refresh")
        if vars:
            for k, v in vars.items():
                args += ["--var", f"{k}={v}"]
        return self._run_cmd(*args).stdout

    def test(self, select: str | None = None) -> str:
        args = ["test"]
        if select:
            args += ["--select", select]
        return self._run_cmd(*args).stdout

    def seed(self) -> str:
        return self._run_cmd("seed").stdout

    def snapshot(self) -> str:
        return self._run_cmd("snapshot").stdout

    def build(self, select: str | None = None) -> str:
        args = ["build"]
        if select:
            args += ["--select", select]
        return self._run_cmd(*args).stdout

    def plan(self) -> str:
        return self._run_cmd("plan").stdout


# ── Dagster ops ───────────────────────────────────────────────────────────── #

def kelpmesh_run_op(select: str | None = None, tag: str | None = None,
                    full_refresh: bool = False):
    """Return a Dagster @op that runs kelpmesh run."""
    dagster = _dagster()

    @dagster.op(required_resource_keys={"kelpmesh"}, name=f"kelpmesh_run")
    def _op(context):
        result = context.resources.kelpmesh.run(
            select=select, tag=tag, full_refresh=full_refresh
        )
        context.log.info(result)
        return result

    return _op


def kelpmesh_test_op(select: str | None = None):
    """Return a Dagster @op that runs kelpmesh test."""
    dagster = _dagster()

    @dagster.op(required_resource_keys={"kelpmesh"}, name="kelpmesh_test")
    def _op(context):
        result = context.resources.kelpmesh.test(select=select)
        context.log.info(result)
        return result

    return _op


def build_kelpmesh_assets(project_dir: str = ".", tags: list[str] | None = None,
                          group_name: str = "kelpmesh"):
    """Create Dagster assets for each kelpmesh tag (or one asset for all models)."""
    dagster = _dagster()

    assets = []
    _tags = tags or ["__all__"]

    for tag in _tags:
        tag_filter = None if tag == "__all__" else tag
        asset_name = f"kelpmesh_{tag.replace('-', '_').replace(' ', '_')}"

        @dagster.asset(
            name=asset_name,
            group_name=group_name,
            description=f"KelpMesh models{' — tag: ' + tag if tag_filter else ''}",
        )
        def _asset(context, _tag=tag_filter, _dir=project_dir):
            resource = KelpMeshResource(project_dir=_dir)
            result = resource.run(tag=_tag)
            context.log.info(result)
            return result

        assets.append(_asset)

    return assets


# ── Dagster sensor (schedule monitor) ────────────────────────────────────── #

def kelpmesh_schedule_sensor(project_dir: str = ".", cron: str = "0 6 * * *",
                              job_name: str = "kelpmesh_daily"):
    """Return a Dagster @schedule that triggers kelpmesh run daily."""
    dagster = _dagster()

    @dagster.schedule(cron_schedule=cron, job_name=job_name)
    def _schedule(context):
        return dagster.RunRequest(run_config={})

    return _schedule
