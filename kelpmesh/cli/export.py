"""kelpmesh export — export semantic layer to BI tool formats."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()
err_console = Console(stderr=True)

FORMATS = ["manifest", "looker", "tableau", "powerbi", "qlik", "all"]


def export_cmd(
    format: str = typer.Option(
        "all",
        "--format", "-f",
        help=f"Export format: {', '.join(FORMATS)}",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Output directory (default: target/exports/<format>)",
    ),
    project_dir: Path = typer.Option(
        Path("."),
        "--project-dir",
        help="kelpmesh project root",
    ),
    project_name: str = typer.Option(
        "",
        "--project-name",
        help="Override project name in exports",
    ),
):
    """Export the semantic layer to BI tool formats.

    Examples:

        kelpmesh export

        kelpmesh export --format looker

        kelpmesh export --format tableau --output ./exports
    """
    from kelpmesh.semantic import ExposureLoader, MetricLoader, SourceLoader
    from kelpmesh.semantic.exporters import EXPORTERS

    if format not in FORMATS:
        err_console.print(f"[red]Unknown format '{format}'. Choose from: {', '.join(FORMATS)}[/red]")
        raise typer.Exit(1)

    proj = project_dir.resolve()
    if not proj.exists():
        err_console.print(f"[red]Project directory not found: {proj}[/red]")
        raise typer.Exit(1)

    metrics = MetricLoader.load(proj)
    sources = SourceLoader.load(proj)
    exposures = ExposureLoader.load(proj)

    if not metrics:
        console.print("[yellow]No metrics found. Create a metrics.yml file in your project.[/yellow]")
        raise typer.Exit(0)

    name = project_name or proj.name
    targets = list(EXPORTERS.keys()) if format == "all" else [format]

    results_table = Table(title="kelpmesh export", show_header=True)
    results_table.add_column("Format", style="cyan")
    results_table.add_column("Files written", style="green")
    results_table.add_column("Output dir", style="dim")

    for fmt in targets:
        exporter_cls = EXPORTERS[fmt]
        exporter = exporter_cls(metrics=metrics, sources=sources, exposures=exposures, project_name=name)
        result = exporter.export()

        out_dir = output if output else proj / "target" / "exports" / fmt
        written = result.write_to(out_dir)

        results_table.add_row(fmt, str(len(written)), str(out_dir))

    console.print(results_table)
    console.print(f"[green]✓[/green] Exported {len(metrics)} metric(s) to {len(targets)} format(s).")
