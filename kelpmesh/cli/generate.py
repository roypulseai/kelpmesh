"""kelpmesh generate — scaffold staging models and schema.yml from source table introspection."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

_console = Console()

_STAGING_TEMPLATE = """\
-- materialized: view
-- description: Staging model for {source_table}
SELECT
{column_list}
FROM {source_ref}
"""

_SCHEMA_TEMPLATE = """\
models:
  - name: {model_name}
    description: "Staging model for {source_table}"
    columns:
{column_entries}
"""


def generate_cmd(
    source: str = typer.Argument(..., help="Source table to scaffold (e.g. 'raw.orders')"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Directory to write generated files"),
    schema: bool = typer.Option(True, "--schema/--no-schema", help="Also generate schema.yml"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing files"),
    project_path: Path = typer.Option(Path("."), "--project-path", "-p", help="Path to kelpmesh project"),
):
    """Scaffold a staging model (and optional schema.yml) from a source table.

    The source table is introspected from the configured warehouse to produce
    column lists automatically.

    Example:
        kelpmesh generate raw.orders
        kelpmesh generate raw.customers --output-dir models/staging
    """
    from kelpmesh.core.project import Project

    try:
        project = Project(project_path)
    except Exception as e:
        _console.print(f"[red]Could not load project: {e}[/red]")
        raise typer.Exit(1)

    parts = source.split(".", 1)
    source_table = parts[-1]
    model_name = f"stg_{source_table}"

    out_dir = output_dir or (project_path / "models" / "staging")
    out_dir.mkdir(parents=True, exist_ok=True)

    model_file = out_dir / f"{model_name}.sql"
    schema_file = out_dir / "schema.yml"

    # Introspect columns from warehouse
    adapter = _get_adapter(project)
    columns = _introspect_columns(adapter, source_table)
    adapter.disconnect()

    if not columns:
        _console.print(
            f"[yellow]Warning: could not introspect '{source_table}' — "
            "generating scaffold with placeholder column.[/yellow]"
        )
        columns = [{"column_name": "id", "data_type": "INTEGER"}]

    # Build SQL
    source_ref = source if "." in source else source_table
    col_lines = "\n".join(f"    {c['column_name']}" + ("," if i < len(columns) - 1 else "") for i, c in enumerate(columns))
    sql_content = _STAGING_TEMPLATE.format(
        source_table=source_table,
        column_list=col_lines,
        source_ref=source_ref,
    )

    # Write model file
    if model_file.exists() and not overwrite:
        _console.print(f"[yellow]Skipping {model_file} (already exists; use --overwrite)[/yellow]")
    else:
        model_file.write_text(sql_content, encoding="utf-8")
        _console.print(f"[green]✓[/green] {model_file}")

    # Write schema.yml
    if schema:
        col_entries = "\n".join(
            f'      - name: {c["column_name"]}\n        data_type: {c["data_type"]}'
            for c in columns
        )
        schema_content = _SCHEMA_TEMPLATE.format(
            model_name=model_name,
            source_table=source_table,
            column_entries=col_entries,
        )

        existing_schema = ""
        if schema_file.exists():
            existing_schema = schema_file.read_text(encoding="utf-8")

        if model_name in existing_schema and not overwrite:
            _console.print(f"[yellow]Skipping schema entry for {model_name} (already in schema.yml)[/yellow]")
        elif schema_file.exists() and not overwrite:
            # Append the new model block to the existing file
            with schema_file.open("a", encoding="utf-8") as f:
                # Strip the leading 'models:' header — it's already there
                lines = schema_content.splitlines(keepends=True)
                body = "".join(lines[1:])  # skip 'models:'
                f.write(body)
            _console.print(f"[green]✓[/green] Appended to {schema_file}")
        else:
            schema_file.write_text(schema_content, encoding="utf-8")
            _console.print(f"[green]✓[/green] {schema_file}")

    _console.print(f"\n[bold]Generated staging model:[/bold] {model_name}")
    _console.print(f"  {len(columns)} columns introspected from [cyan]{source}[/cyan]")


def _get_adapter(project):
    cfg = project.config.warehouse
    if cfg.type == "duckdb":
        from kelpmesh.adapters.duckdb import DuckDBAdapter
        a = DuckDBAdapter(cfg, project_path=str(project.path))
        a.connect()
        return a
    # Fall back — return a dummy adapter that returns no columns
    return _NullAdapter()


def _introspect_columns(adapter, table_name: str) -> list[dict]:
    try:
        rows = adapter.table_schema(table_name)
        return rows or []
    except Exception:
        return []


class _NullAdapter:
    def table_schema(self, *a, **kw):
        return []

    def disconnect(self):
        pass
