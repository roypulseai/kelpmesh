"""kelpmesh format — auto-format all SQL model files using sqlglot pretty-printing.

Reads every .sql file under the models/ directory, transpiles it through sqlglot
with the requested dialect, and writes the pretty-printed SQL back in place.

Use --check to verify formatting without writing (useful in CI), and --diff to
inspect exactly what would change before committing to rewrites.
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

# Dialects accepted by sqlglot that kelpmesh exposes.
_VALID_DIALECTS = {
    "ansi", "duckdb", "snowflake", "bigquery", "spark",
    "trino", "tsql", "hive", "mysql", "presto",
}


def _collect_sql_files(models_dir: Path, model_filter: list[str] | None) -> list[Path]:
    """Return sorted list of .sql files under models_dir, optionally filtered by name."""
    all_files = sorted(models_dir.rglob("*.sql"))
    if not model_filter:
        return all_files
    # Match on stem (filename without extension) or full relative path fragment.
    filtered = []
    for f in all_files:
        if any(name in (f.stem, str(f)) for name in model_filter):
            filtered.append(f)
    return filtered


def _format_sql(sql: str, dialect: str) -> tuple[str, str | None]:
    """Return (formatted_sql, error_message).  error_message is None on success."""
    try:
        import sqlglot

        result = sqlglot.transpile(
            sql,
            read=dialect if dialect != "ansi" else None,
            write=dialect if dialect != "ansi" else None,
            pretty=True,
        )
        formatted = "\n\n".join(result) if result else sql
        # Ensure single trailing newline.
        return formatted.rstrip() + "\n", None
    except Exception as exc:  # noqa: BLE001
        return sql, str(exc)


def _unified_diff(original: str, formatted: str, filename: str) -> str:
    """Return a unified diff string between original and formatted SQL."""
    original_lines = original.splitlines(keepends=True)
    formatted_lines = formatted.splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
            original_lines,
            formatted_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )
    return "".join(diff_lines)


def format_cmd(
    models: list[str] = typer.Argument(None, help="Model names to format (default: all)"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    check: bool = typer.Option(
        False,
        "--check",
        help="Exit 1 if any file would change; do not write files (useful in CI).",
    ),
    diff: bool = typer.Option(
        False,
        "--diff",
        help="Show a unified diff of changes without writing files.",
    ),
    select: list[str] = typer.Option(None, "--select", "-s", help="Model name selection filter"),
    dialect: str = typer.Option(
        "ansi",
        "--dialect",
        help=(
            "SQL dialect for formatting. "
            "Options: ansi, duckdb, snowflake, bigquery, spark, trino, tsql, hive, mysql, presto."
        ),
    ),
):
    """Auto-format SQL model files using sqlglot pretty-printing.

    Walks the models/ directory and reformats every .sql file in-place.
    Use --check in CI to enforce formatting without modifying files.
    Use --diff to preview changes before writing.

    Examples:
        kelpmesh format                          # format all models
        kelpmesh format orders_daily             # format one model by name
        kelpmesh format --check                  # CI check — exit 1 if unformatted
        kelpmesh format --diff                   # show what would change
        kelpmesh format --dialect duckdb         # use DuckDB dialect
        kelpmesh format --select orders_daily    # filter by model name
    """
    if dialect not in _VALID_DIALECTS:
        console.print(
            f"[red]Unknown dialect '{dialect}'. "
            f"Valid options: {', '.join(sorted(_VALID_DIALECTS))}[/red]"
        )
        raise typer.Exit(2)

    project_path = project_dir.resolve()
    models_dir = project_path / "models"

    if not models_dir.exists():
        console.print(f"[red]Models directory not found: {models_dir}[/red]")
        raise typer.Exit(1)

    combined_filter = list(models or []) + list(select or [])
    sql_files = _collect_sql_files(models_dir, combined_filter or None)

    if not sql_files:
        console.print("[yellow]No SQL files found.[/yellow]")
        raise typer.Exit(0)

    reformatted: list[str] = []
    already_ok: list[str] = []
    errors: list[tuple[str, str]] = []
    would_change: list[str] = []  # for --check mode

    for sql_file in sql_files:
        original = sql_file.read_text(encoding="utf-8")
        formatted, err = _format_sql(original, dialect)

        if err:
            rel = sql_file.relative_to(project_path)
            errors.append((str(rel), err))
            console.print(f"[yellow]  warn[/yellow]  {rel}  [dim]({err[:80]})[/dim]")
            continue

        rel = str(sql_file.relative_to(project_path))

        if formatted == original:
            already_ok.append(rel)
            continue

        if check:
            would_change.append(rel)
            console.print(f"[red]  ✗[/red]  {rel}  [dim]would reformat[/dim]")
        elif diff:
            diff_text = _unified_diff(original, formatted, rel)
            if diff_text:
                # Color the diff output: additions green, removals red.
                for line in diff_text.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        console.print(Text(line, style="green"))
                    elif line.startswith("-") and not line.startswith("---"):
                        console.print(Text(line, style="red"))
                    elif line.startswith("@@"):
                        console.print(Text(line, style="cyan"))
                    else:
                        console.print(line)
        else:
            sql_file.write_text(formatted, encoding="utf-8")
            reformatted.append(rel)

    # Summary table
    console.print()
    console.print(f"[bold]kelpmesh format[/bold]  [dim]{project_path.name}[/dim]  [dim](dialect: {dialect})[/dim]")
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Outcome", style="bold", min_width=18)
    table.add_column("Count", justify="right")

    if check:
        table.add_row("[green]Already formatted[/green]", str(len(already_ok)))
        table.add_row("[red]Would reformat[/red]", str(len(would_change)))
    elif diff:
        table.add_row("[cyan]Would reformat[/cyan]", str(len([f for f in sql_files if f not in already_ok and str(f.relative_to(project_path)) not in [e[0] for e in errors]])))
        table.add_row("[green]Already formatted[/green]", str(len(already_ok)))
    else:
        table.add_row("[green]Reformatted[/green]", str(len(reformatted)))
        table.add_row("[dim]Already formatted[/dim]", str(len(already_ok)))

    if errors:
        table.add_row("[yellow]Parse errors (skipped)[/yellow]", str(len(errors)))

    console.print(table)
    console.print()

    if check and would_change:
        console.print(
            "[red]Formatting check failed.[/red]  "
            "Run [bold]kelpmesh format[/bold] to fix."
        )
        raise typer.Exit(1)
