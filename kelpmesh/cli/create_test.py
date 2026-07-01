"""kelpmesh create_test — generate YAML fixture tests from live warehouse data.

Captures sample rows from upstream models, runs the target model against them
in-memory, and saves the input/output pairs as a YAML fixture file.

After generation, the fixture runs entirely offline (no warehouse needed):
    kelpmesh test                          # runs all SQL + YAML fixture tests
    kelpmesh test --select my_model        # runs tests for a specific model

Usage:
    kelpmesh create_test stg_payments
    kelpmesh create_test stg_payments --limit 5
    kelpmesh create_test stg_payments --output tests/my_fixture.yaml
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console

console = Console()


def create_test_cmd(
    model_name: str = typer.Argument(..., help="Model to generate a fixture test for"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    limit: int = typer.Option(5, "--limit", "-n", help="Number of rows to capture per upstream model"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output YAML file (default: tests/<model_name>.yaml)"
    ),
    target: Optional[str] = typer.Option(
        None, "--target",
        help="Active target from kelpmesh.yml (dev/prod/staging)"
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing fixture file"),
):
    """Generate a YAML fixture test from live warehouse data.

    Queries upstream models for sample rows, runs the model logic in-memory,
    and saves the result as a reproducible fixture that runs without a warehouse.

    Examples:
        kelpmesh create_test stg_payments
        kelpmesh create_test stg_payments --limit 10
        kelpmesh create_test orders --output tests/orders_fixture.yaml
    """
    from kelpmesh.adapters import get_adapter
    from kelpmesh.adapters.base import sanitize_name
    from kelpmesh.core.config import ProjectConfig
    from kelpmesh.core.project import Project
    from kelpmesh.core.substitutions import apply as apply_substitutions

    project_path = project_dir.resolve()
    config = ProjectConfig.load(project_path, target=target)
    project = Project(project_path)

    model = project.get_model(model_name)
    if not model:
        console.print(f"[red]Model '{model_name}' not found.[/red]")
        raise typer.Exit(1)

    if model.language == "python":
        console.print("[red]create_test does not support Python models.[/red]")
        raise typer.Exit(1)

    adapter = get_adapter(config.warehouse, project_path=str(project_path))

    console.print(f"\n[bold]kelpmesh create_test[/bold]  [cyan]{model_name}[/cyan]")
    console.print(f"  Querying {len(model.upstream)} upstream model(s), {limit} rows each\n")

    inputs: dict[str, list[dict]] = {}

    for upstream_name in sorted(model.upstream):
        try:
            rows = adapter.execute(f"SELECT * FROM {sanitize_name(upstream_name)} LIMIT {limit}")
            if rows:
                inputs[upstream_name] = [dict(row) for row in rows]
                console.print(f"  [green]✓[/green] {upstream_name}: {len(inputs[upstream_name])} rows")
            else:
                inputs[upstream_name] = []
                console.print(f"  [yellow]![/yellow] {upstream_name}: 0 rows (table may be empty)")
        except Exception as e:
            console.print(f"  [red]✗[/red] {upstream_name}: {e}")
            adapter.disconnect()
            raise typer.Exit(1)

    # Run the model SQL in-memory against the captured inputs
    console.print()
    actual_output: list[dict] = []
    try:
        import duckdb
        conn = duckdb.connect(":memory:")

        from kelpmesh.testing.fixtures import _create_table_from_rows
        for tbl_name, rows in inputs.items():
            plain = tbl_name.split(".")[-1]
            _create_table_from_rows(conn, plain, rows)

        raw_sql = model.sql or ""
        # Apply variable substitutions
        sql = apply_substitutions(
            raw_sql,
            vars=project.config.vars,
            table_name=model_name,
            is_incremental=False,
        )
        # Replace qualified refs with plain names
        import re
        for qname in sorted(inputs.keys(), key=len, reverse=True):
            plain = qname.split(".")[-1]
            sql = re.sub(
                r'(?<!["\w])' + re.escape(qname) + r'(?!["\w])',
                plain,
                sql,
            )

        df = conn.execute(sql).fetchdf()
        actual_output = df.to_dict(orient="records")
        conn.close()

        console.print(f"  [green]✓[/green] Model ran — {len(actual_output)} output rows captured")

    except ImportError:
        console.print("[red]duckdb not installed. Run: pip install duckdb[/red]")
        adapter.disconnect()
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"  [yellow]![/yellow] Model dry-run failed: {e}")
        console.print("  [dim]Writing fixture with empty outputs — fill in manually.[/dim]")

    adapter.disconnect()

    # Build fixture structure
    fixture_key = f"test_{model_name}"
    fixture: dict = {
        fixture_key: {
            "model": f"{project.config.name}.{model_name}",
            "inputs": inputs,
            "outputs": {"query": actual_output},
        }
    }

    # Determine output path
    out_path = output or (project_path / project.config.tests_path / f"{model_name}.yaml")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and not overwrite:
        console.print(
            f"\n[yellow]File exists: {out_path.relative_to(project_path)}[/yellow]  "
            f"Use [bold]--overwrite[/bold] to replace."
        )
        raise typer.Exit(1)

    # Serialize — convert any non-YAML-safe types
    serializable = _make_serializable(fixture)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(serializable, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    console.print(f"\n[green]✓[/green] Fixture written → [cyan]{out_path.relative_to(project_path)}[/cyan]")
    console.print("\nRun it with: [bold cyan]kelpmesh test[/bold cyan]")


def _make_serializable(obj):
    """Recursively convert pandas/numpy types to Python native for YAML serialization."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_serializable(v) for v in obj]
    # pandas NA / numpy types
    try:
        import pandas as pd
        if pd.isna(obj):
            return None
    except (ImportError, TypeError, ValueError):
        pass
    try:
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
    except ImportError:
        pass
    return obj
