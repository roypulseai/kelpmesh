import importlib.metadata
import os
import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    os.environ["PYTHONUTF8"] = "1"


import typer
from rich.console import Console
from rich.panel import Panel

from kelpmesh.core.errors import sanitize_exception_message

DEBUG_FLAG: bool = False
_err_console = Console(stderr=True, force_terminal=True)

try:
    __version__ = importlib.metadata.version("kelpmesh-core")
except importlib.metadata.PackageNotFoundError:
    __version__ = "1.0.3"


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
                "kelpmesh prohibits telemetry/analytics packages."
            )
            sys.exit(1)


_validate_no_telemetry()


def fmt_error(exc: Exception):
    msg = str(exc)
    if "No such table" in msg or "does not exist" in msg:
        _err_console.print("[red]Table not found.[/red] Run upstream models first with [bold]kelpmesh run[/bold].")
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
    name="kelpmesh",
    help="kelpmesh - Code-native data transformation (SQL & Python models)",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
    rich_help_panel="Quick Start" if False else None,
)


def _version_callback(show_version: bool = False):
    if show_version:
        _console = Console(force_terminal=True)
        _console.print(f"kelpmesh-core version [bold]{__version__}[/bold]")
        raise typer.Exit()


@app.callback()
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=_version_callback,
        is_eager=True, help="Show the kelpmesh version and exit",
    ),
    debug: bool = typer.Option(False, "--debug", help="Show full tracebacks on errors"),
):
    global DEBUG_FLAG
    DEBUG_FLAG = debug


from kelpmesh.cli.build import build_cmd
from kelpmesh.cli.ci import ci_app
from kelpmesh.cli.clean import clean_cmd
from kelpmesh.cli.compare import compare_cmd
from kelpmesh.cli.compile import compile_cmd
from kelpmesh.cli.create_test import create_test_cmd
from kelpmesh.cli.debug import debug_cmd
from kelpmesh.cli.deps import deps_cmd
from kelpmesh.cli.diff import diff_cmd
from kelpmesh.cli.docs import docs_app
from kelpmesh.cli.export import export_cmd
from kelpmesh.cli.exposures import exposure_app
from kelpmesh.cli.format import format_cmd
from kelpmesh.cli.freshness import freshness_cmd
from kelpmesh.cli.generate import generate_cmd
from kelpmesh.cli.history import history_cmd
from kelpmesh.cli.import_dbt import import_cmd
from kelpmesh.cli.init import init_cmd
from kelpmesh.cli.lint import lint_cmd
from kelpmesh.cli.ls import ls_cmd
from kelpmesh.cli.mesh import mesh_app
from kelpmesh.cli.metrics import metric_app
from kelpmesh.cli.orchestrate import orchestrate_cmd
from kelpmesh.cli.package_cli import package_app
from kelpmesh.cli.plan import plan_cmd
from kelpmesh.cli.pre_commit import pre_commit_cmd
from kelpmesh.cli.preview import preview_cmd
from kelpmesh.cli.rollback import rollback_cmd
from kelpmesh.cli.run import run_cmd
from kelpmesh.cli.scan import scan_app
from kelpmesh.cli.schedule import schedule_app
from kelpmesh.cli.schema import schema_cmd
from kelpmesh.cli.security import security_app
from kelpmesh.cli.seed import seed_cmd
from kelpmesh.cli.serve import serve_cmd
from kelpmesh.cli.sources import source_app
from kelpmesh.cli.studio import studio_cmd
from kelpmesh.cli.test import test_cmd

# ── Quick Start panel ────────────────────────────────────────────────────
app.command(name="init", rich_help_panel="Quick Start")(init_cmd)
app.command(name="seed", rich_help_panel="Quick Start")(seed_cmd)
app.command(name="run", rich_help_panel="Quick Start")(run_cmd)
app.command(name="test", rich_help_panel="Quick Start")(test_cmd)

# ── Commands panel ───────────────────────────────────────────────────────
app.command(name="build", rich_help_panel="Commands")(build_cmd)
app.command(name="diff", rich_help_panel="Commands")(diff_cmd)
app.add_typer(docs_app, name="docs")
app.command(name="import", rich_help_panel="Commands")(import_cmd)
app.command(name="preview", rich_help_panel="Commands")(preview_cmd)
app.command(name="ls", rich_help_panel="Commands")(ls_cmd)
app.command(name="clean", rich_help_panel="Commands")(clean_cmd)
app.command(name="debug", rich_help_panel="Commands")(debug_cmd)
app.command(name="pre-commit", rich_help_panel="Commands")(pre_commit_cmd)
app.command(name="compare", rich_help_panel="Commands")(compare_cmd)
app.command(name="deps", rich_help_panel="Commands")(deps_cmd)
app.command(name="orchestrate", rich_help_panel="Commands")(orchestrate_cmd)

schema_app = typer.Typer(help="Schema inspection and drift detection")
schema_app.command(name="diff")(schema_cmd)
app.add_typer(schema_app, name="schema")

# ── Analysis / Planning panel ────────────────────────────────────────────
app.command(name="plan", rich_help_panel="Analysis")(plan_cmd)
app.command(name="compile", rich_help_panel="Analysis")(compile_cmd)
app.command(name="history", rich_help_panel="Analysis")(history_cmd)
app.command(name="freshness", rich_help_panel="Analysis")(freshness_cmd)
app.command(name="generate", rich_help_panel="Analysis")(generate_cmd)
app.command(name="rollback", rich_help_panel="Analysis")(rollback_cmd)

# ── Quality panel ────────────────────────────────────────────────────────
app.command(name="format", rich_help_panel="Quality")(format_cmd)
app.command(name="lint", rich_help_panel="Quality")(lint_cmd)
app.command(name="create-test", rich_help_panel="Quality")(create_test_cmd)
app.add_typer(scan_app, name="scan")
app.add_typer(security_app, name="security")

# ── Integrations panel ───────────────────────────────────────────────────
app.add_typer(source_app, name="source")
app.add_typer(exposure_app, name="exposure")
app.add_typer(metric_app, name="metric")
app.add_typer(mesh_app, name="mesh")
app.add_typer(package_app, name="package")
app.add_typer(schedule_app, name="schedule")
app.add_typer(ci_app, name="ci")
app.command(name="studio", rich_help_panel="Integrations")(studio_cmd)
app.command(name="export", rich_help_panel="Integrations")(export_cmd)
app.command(name="serve", rich_help_panel="Integrations")(serve_cmd)


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
