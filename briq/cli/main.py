import sys
import os
import traceback

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    os.environ["PYTHONUTF8"] = "1"

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from briq.core.errors import sanitize_exception_message

DEBUG_FLAG: bool = False
_err_console = Console(stderr=True, force_terminal=True)


def _validate_no_telemetry():
    """Guard: refuse to load if any telemetry package is present."""
    telemetry_pkgs = [
        "posthog", "sentry_sdk", "datadog", "statsd", "telemetry",
        "analytics", "segment", "amplitude", "mixpanel",
    ]
    for pkg in telemetry_pkgs:
        if pkg in sys.modules:
            _err_console.print(
                f"[red]Security block:[/red] {pkg} is loaded. "
                "briq prohibits telemetry/analytics packages."
            )
            sys.exit(1)


_validate_no_telemetry()


def fmt_error(exc: Exception):
    msg = str(exc)
    if "No such table" in msg or "does not exist" in msg:
        _err_console.print("[red]Table not found.[/red] Run upstream models first with [bold]briq run[/bold].")
    elif "Cycle detected" in msg or "cycle" in msg.lower():
        _err_console.print(f"[red]{msg}[/red]")
        _err_console.print("[yellow]Fix the circular dependency in your model references.[/yellow]")
    elif "No module named" in msg:
        _err_console.print(f"[red]Missing dependency: {msg}[/red]")
        parts = msg.split("'")
        if len(parts) >= 2:
            _err_console.print(f"[yellow]Install it with: pip install {parts[1]}[/yellow]")
    else:
        _err_console.print(f"[red]Error: {sanitize_exception_message(msg)}[/red]")
        _err_console.print("[yellow]Run with --debug to see the full traceback.[/yellow]")


app = typer.Typer(
    name="briq",
    help="briq — Pure SQL transformation and data modelling platform",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
)


@app.callback()
def main_callback(
    ctx: typer.Context,
    debug: bool = typer.Option(False, "--debug", help="Show full tracebacks on errors"),
):
    global DEBUG_FLAG
    DEBUG_FLAG = debug


from briq.cli.run import run_cmd
from briq.cli.test import test_cmd
from briq.cli.build import build_cmd
from briq.cli.diff import diff_cmd
from briq.cli.docs import docs_cmd, manifest_cmd
from briq.cli.init import init_cmd
from briq.cli.import_dbt import import_cmd
from briq.cli.seed import seed_cmd
from briq.cli.preview import preview_cmd
from briq.cli.schema import schema_cmd
from briq.cli.ls import ls_cmd
from briq.cli.clean import clean_cmd
from briq.cli.debug import debug_cmd
from briq.cli.pre_commit import pre_commit_cmd
from briq.cli.compare import compare_cmd
from briq.cli.deps import deps_cmd
from briq.cli.orchestrate import orchestrate_cmd
from briq.cli.scan import scan_app
from briq.cli.security import security_app
from briq.cli.sources import source_app
from briq.cli.exposures import exposure_app
from briq.cli.metrics import metric_app
from briq.cli.package_cli import package_app
from briq.cli.generate import generate_cmd
from briq.cli.plan import plan_cmd
from briq.cli.history import history_cmd
from briq.cli.freshness import freshness_cmd
from briq.cli.studio import studio_cmd
from briq.cli.export import export_cmd
from briq.cli.serve import serve_cmd
from briq.cli.mesh import mesh_app

app.command(name="init")(init_cmd)
app.command(name="run")(run_cmd)
app.command(name="test")(test_cmd)
app.command(name="build")(build_cmd)
app.command(name="diff")(diff_cmd)
app.command(name="docs")(docs_cmd)
app.command(name="docs-manifest")(manifest_cmd)
app.command(name="import")(import_cmd)
app.command(name="seed")(seed_cmd)
app.command(name="preview")(preview_cmd)
app.command(name="ls")(ls_cmd)
app.command(name="clean")(clean_cmd)
app.command(name="debug")(debug_cmd)
app.command(name="pre-commit")(pre_commit_cmd)
app.command(name="compare")(compare_cmd)
app.command(name="deps")(deps_cmd)
app.command(name="orchestrate")(orchestrate_cmd)

schema_app = typer.Typer(help="Schema inspection and drift detection")
schema_app.command(name="diff")(schema_cmd)
app.add_typer(schema_app, name="schema")

app.add_typer(scan_app, name="scan")
app.add_typer(security_app, name="security")
app.add_typer(source_app, name="source")
app.add_typer(exposure_app, name="exposure")
app.add_typer(metric_app, name="metric")
app.add_typer(package_app, name="package")
app.command(name="generate")(generate_cmd)
app.command(name="plan")(plan_cmd)
app.command(name="history")(history_cmd)
app.command(name="freshness")(freshness_cmd)
app.command(name="studio")(studio_cmd)
app.command(name="export")(export_cmd)
app.command(name="serve")(serve_cmd)
app.add_typer(mesh_app, name="mesh")


def main():
    try:
        app()
    except typer.Exit:
        raise
    except Exception as e:
        if DEBUG_FLAG:
            _err_console.print(f"[red]Error: {e}[/red]")
            traceback.print_exc()
        else:
            fmt_error(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
