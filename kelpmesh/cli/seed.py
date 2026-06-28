"""kelpmesh seed — load CSV/TSV files from seeds/ directory or a specific file."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from kelpmesh.adapters import get_adapter
from kelpmesh.core.config import ProjectConfig
from kelpmesh.core.errors import sanitize_exception_message

console = Console()

# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_BOOL_VALS = {"true", "false", "1", "0", "yes", "no", "t", "f"}


def _infer_type(values: list[str]) -> str:
    """Return a SQL type name inferred from a sample of string values."""
    non_null = [v.strip() for v in values if v.strip() and v.strip().lower() not in ("", "null", "none")]
    if not non_null:
        return "VARCHAR"
    sample = non_null[:500]
    # Boolean
    if all(v.lower() in _BOOL_VALS for v in sample):
        return "BOOLEAN"
    # Integer
    try:
        for v in sample:
            int(v)
        return "BIGINT"
    except ValueError:
        pass
    # Float
    try:
        for v in sample:
            float(v.replace(",", ""))
        return "DOUBLE"
    except ValueError:
        pass
    # Date
    if all(_DATE_RE.match(v) for v in sample):
        return "DATE"
    # Timestamp
    if all(_TS_RE.match(v) for v in sample):
        return "TIMESTAMP"
    return "VARCHAR"


def _load_schema_overrides(seeds_dir: Path) -> dict[str, dict[str, str]]:
    """Read optional seeds.yml for explicit column types."""
    import yaml

    overrides: dict[str, dict[str, str]] = {}
    schema_file = seeds_dir / "seeds.yml"
    if not schema_file.exists():
        return overrides
    data = yaml.safe_load(schema_file.read_text(encoding="utf-8")) or {}
    for seed in data.get("seeds", []):
        name = seed.get("name", "")
        overrides[name] = seed.get("column_types", {})
    return overrides


def _csv_to_create_table_sql(
    path: Path,
    table_name: str,
    delimiter: str = ",",
    column_types: dict[str, str] | None = None,
) -> tuple[str, list[list[str]], list[str]]:
    """Parse CSV, infer types, return (CREATE TABLE SQL, rows, col_names)."""
    column_types = column_types or {}
    text = path.read_text(encoding="utf-8-sig")  # utf-8-sig strips BOM
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return f"CREATE TABLE IF NOT EXISTS {table_name} (placeholder VARCHAR)", [], []

    headers = [h.strip() for h in rows[0]]
    data_rows = rows[1:]

    # Build column samples for inference
    col_samples: dict[str, list[str]] = {h: [] for h in headers}
    for row in data_rows[:1000]:
        for i, val in enumerate(row):
            if i < len(headers):
                col_samples[headers[i]].append(val)

    col_defs = []
    for col in headers:
        sql_type = column_types.get(col) or _infer_type(col_samples[col])
        col_defs.append(f'  "{col}" {sql_type}')

    ddl = f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n' + ",\n".join(col_defs) + "\n)"
    return ddl, data_rows, headers


def _load_csv_generic(adapter, path: Path, table_name: str, delimiter: str, column_types: dict | None):
    """Load CSV into any adapter using CREATE TABLE + INSERT (portable fallback)."""
    from kelpmesh.adapters.duckdb import DuckDBAdapter

    # DuckDB: use native read_csv_auto for speed
    if isinstance(adapter, DuckDBAdapter):
        adapter.load_csv(str(path.resolve()), table_name, delimiter=delimiter)
        return

    ddl, data_rows, headers = _csv_to_create_table_sql(path, table_name, delimiter, column_types)
    adapter.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    adapter.execute(ddl)
    if not data_rows:
        return
    col_list = ", ".join(f'"{h}"' for h in headers)
    placeholders = ", ".join(["%s"] * len(headers))
    insert_sql = f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'

    # Batch into chunks of 1000
    batch: list[tuple] = []
    for row in data_rows:
        padded = row + [""] * max(0, len(headers) - len(row))
        batch.append(tuple(padded[: len(headers)]))
        if len(batch) >= 1000:
            for r in batch:
                adapter.execute(insert_sql % tuple(f"'{v}'" for v in r))
            batch = []
    for r in batch:
        adapter.execute(insert_sql % tuple(f"'{v}'" for v in r))


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

def seed_cmd(
    seed_file: Optional[Path] = typer.Argument(
        None, help="Seed file (.sql / .csv / .tsv). Omit to load all files in seeds/"
    ),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    table_name: Optional[str] = typer.Option(None, "--table", "-t", help="Target table name"),
    select: Optional[str] = typer.Option(None, "--select", "-s", help="Load one seed by name"),
    full_refresh: bool = typer.Option(False, "--full-refresh", "-f", help="Drop and recreate table"),
):
    """Load seed data from a file or from the seeds/ directory.

    With no arguments, scans seeds/ and loads every CSV/TSV/SQL file.
    Column types are inferred automatically; override them in seeds/seeds.yml.

    Examples:
        kelpmesh seed                       # load all seeds
        kelpmesh seed seeds/countries.csv   # load one file
        kelpmesh seed --select countries    # same, by name
    """
    project_path = project_dir.resolve()
    config = ProjectConfig.load(project_path)
    adapter = get_adapter(config.warehouse, project_path=str(project_path))

    seeds_dir = project_path / config.seeds_path
    schema_overrides = _load_schema_overrides(seeds_dir) if seeds_dir.exists() else {}

    # Build list of (path, table_name) pairs to load
    files_to_load: list[tuple[Path, str]] = []

    if seed_file:
        files_to_load.append((seed_file.resolve(), table_name or seed_file.stem))
    elif select:
        candidates = list(seeds_dir.rglob(f"{select}.*")) if seeds_dir.exists() else []
        if not candidates:
            console.print(f"[red]No seed file found for '{select}' in {seeds_dir}[/red]")
            raise typer.Exit(1)
        files_to_load.append((candidates[0], select))
    else:
        # Scan seeds/ directory
        if not seeds_dir.exists():
            console.print(f"[yellow]seeds/ directory not found at {seeds_dir}. Nothing to load.[/yellow]")
            raise typer.Exit(0)
        for f in sorted(seeds_dir.rglob("*")):
            if f.suffix.lower() in (".csv", ".tsv", ".sql") and f.name != "seeds.yml":
                files_to_load.append((f, f.stem))

    if not files_to_load:
        console.print("[yellow]No seed files found.[/yellow]")
        raise typer.Exit(0)

    console.print(f"\n[bold]kelpmesh seed[/bold]  [dim]{project_path.name}[/dim]\n")

    results_table = Table(box=None, padding=(0, 1), show_header=False)
    results_table.add_column("icon", width=3)
    results_table.add_column("name", style="cyan")
    results_table.add_column("detail", style="dim")

    ok = err = 0
    for fpath, tname in files_to_load:
        suffix = fpath.suffix.lower()
        try:
            if full_refresh:
                try:
                    adapter.execute(f'DROP TABLE IF EXISTS "{tname}"')
                except Exception:
                    pass

            if suffix == ".sql":
                adapter.execute(fpath.read_text(encoding="utf-8"))
                detail = "SQL executed"
            elif suffix in (".csv", ".tsv"):
                delim = "," if suffix == ".csv" else "\t"
                col_types = schema_overrides.get(tname, {})
                _load_csv_generic(adapter, fpath, tname, delim, col_types)
                detail = f"loaded → {tname}"
            else:
                detail = f"skipped (unsupported: {suffix})"
                results_table.add_row("[dim]–[/dim]", tname, detail)
                continue

            results_table.add_row("[green]✓[/green]", tname, detail)
            ok += 1
        except Exception as e:
            msg = sanitize_exception_message(str(e))
            results_table.add_row("[red]✗[/red]", tname, f"[red]{msg}[/red]")
            err += 1

    console.print(results_table)
    console.print()
    parts = []
    if ok:
        parts.append(f"[green]{ok} loaded[/green]")
    if err:
        parts.append(f"[red]{err} failed[/red]")
    console.print("  " + " · ".join(parts))
    console.print()

    adapter.disconnect()
    if err:
        raise typer.Exit(1)
