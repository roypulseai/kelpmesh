"""kelpmesh compile — render all template expressions and write compiled SQL to target/compiled/.

Unlike `kelpmesh run`, this command never touches the warehouse.  It lets you
inspect exactly what SQL kelpmesh will execute, including:
  - {{ var("name") }} substitutions
  - {{ env_var("NAME") }} substitutions
  - {{ is_incremental() }} / {% if is_incremental() %} blocks
  - {{ this }} references
  - Ephemeral model CTE inlining

This is useful for code review, debugging variable substitutions, and
understanding incremental model logic before running it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.syntax import Syntax

from kelpmesh.core.project import Project
from kelpmesh.core.executor import Executor
from kelpmesh.core.substitutions import apply as apply_substitutions, parse_cli_vars
from kelpmesh.adapters import get_adapter
from kelpmesh.state.engine import StateEngine

console = Console()


def compile_cmd(
    models: list[str] = typer.Argument(None, help="Model names to compile (default: all)"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    select: list[str] = typer.Option(None, "--select", "-s", help="Model selection"),
    tag: list[str] = typer.Option(None, "--tag", help="Compile models with this tag"),
    var: list[str] = typer.Option(None, "--var", help="Set a variable: key=value"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Write compiled SQL to this directory (default: target/compiled/)"
    ),
    print_sql: bool = typer.Option(
        False, "--print", help="Print compiled SQL to stdout instead of writing files"
    ),
    is_incremental: bool = typer.Option(
        False, "--incremental",
        help="Render as if tables already exist (incremental=true)"
    ),
    env: Optional[str] = typer.Option(
        None, "--env", "-e",
        help="Target environment (dev/staging/prod) — applies env prefix to table names in compiled output"
    ),
    target: Optional[str] = typer.Option(
        None, "--target", help="Active profile from kelpmesh.yml targets"
    ),
):
    """Compile model SQL — apply all variable substitutions without running.

    Writes compiled SQL to target/compiled/<model>.sql by default.

    Examples:
        kelpmesh compile                      # compile all models
        kelpmesh compile orders_daily         # compile one model
        kelpmesh compile --select +orders     # compile orders and its upstream deps
        kelpmesh compile --var start=2025-01  # with variable override
        kelpmesh compile --print orders       # print to stdout
    """
    from kelpmesh.core.config import ProjectConfig
    project_path = project_dir.resolve()
    config = ProjectConfig.load(project_path, target=target)
    project = Project(project_path)
    project.config = config

    if not project.models:
        console.print("[yellow]No models found.[/yellow]")
        raise typer.Exit(0)

    cli_vars = parse_cli_vars(list(var) if var else [])
    merged_vars = {**config.vars, **cli_vars}

    adapter = get_adapter(config.warehouse, project_path=str(project.path))
    state = StateEngine(project.path)
    executor = Executor(project, adapter, state, vars=merged_vars, env=env)

    dag = executor.dag
    dag.build()

    if select or tag:
        names = dag.select_models(select=select or None, tags=list(tag) if tag else None)
    elif models:
        names = models
    else:
        names = dag.execution_order()

    out_dir = output or (project.path / project.config.target_path / "compiled")
    if not print_sql:
        out_dir.mkdir(parents=True, exist_ok=True)

    compiled: list[tuple[str, str]] = []
    for name in names:
        model = project.get_model(name)
        if not model or model.language != "sql":
            continue
        if model.materialized in ("ephemeral",):
            continue  # ephemerals are inlined; not compiled standalone

        raw_sql = executor.resolve_ephemeral(name)
        table_name = executor._effective_table_name(model)
        sql = apply_substitutions(
            raw_sql,
            vars=merged_vars,
            table_name=table_name,
            is_incremental=is_incremental,
        )
        compiled.append((name, sql))

    if not compiled:
        console.print("[yellow]No models to compile.[/yellow]")
        state.close(); adapter.disconnect()
        raise typer.Exit(0)

    if print_sql:
        for name, sql in compiled:
            console.print(f"\n[bold dim]-- {name}[/bold dim]")
            console.print(Syntax(sql.strip(), "sql", theme="monokai", word_wrap=True))
    else:
        for name, sql in compiled:
            out_file = out_dir / f"{name}.sql"
            out_file.write_text(sql.strip() + "\n", encoding="utf-8")
        console.print(f"\n[bold]kelpmesh compile[/bold]  [dim]{project.path.name}[/dim]")
        console.print(f"\n  [green]✓[/green] {len(compiled)} models compiled → [dim]{out_dir}[/dim]\n")

    state.close()
    adapter.disconnect()
