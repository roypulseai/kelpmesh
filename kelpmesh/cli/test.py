import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from kelpmesh.core.project import Project
from kelpmesh.core.schema_yaml import SchemaYaml
from kelpmesh.testing.runner import TestRunner
from kelpmesh.testing.schema_tests import SchemaTestGenerator
from kelpmesh.testing.fixtures import FixtureTestRunner
from kelpmesh.adapters import get_adapter
from kelpmesh.core.packages import _packages_dir

console = Console()


def test_cmd(
    model: str = typer.Argument(None, help="Model name to test (default: all)"),
    project_dir: Path = typer.Option(
        ".", "--project-dir", "-p", help="Project directory"
    ),
    select: list[str] = typer.Option(
        None, "--select", "-s", help="Select models by name or tag: model, +upstream, tag:name"
    ),
    warn: bool = typer.Option(False, "--warn", "-w", help="Treat test failures as warnings, not errors"),
    store_failures: bool = typer.Option(
        False, "--store-failures",
        help="Write failing rows to a table in the warehouse (test_failures)"
    ),
    env: Optional[str] = typer.Option(
        None, "--env", "-e",
        help="Target environment — used to name the failures table (e.g. dev_test_failures)"
    ),
    target: Optional[str] = typer.Option(
        None, "--target", help="Active profile from kelpmesh.yml targets"
    ),
    generate: str = typer.Option(None, "--generate", "-g", help="Generate test from expectation (not_null, unique, etc.)"),
    arg: list[str] = typer.Option([], "--arg", "-a", help="Template arguments (key=value)"),
):
    """Run tests for one or all models.

    Runs both SQL assertion tests (tests/*.sql) and YAML fixture tests (tests/*.yaml).

    Examples:
        kelpmesh test                          # run all tests
        kelpmesh test orders                   # run tests for the orders model
        kelpmesh test --select +orders         # run tests for orders and upstream deps
        kelpmesh test --store-failures         # persist failures to warehouse table
        kelpmesh test --warn                   # non-fatal mode (exit 0 even with failures)
    """
    from kelpmesh.core.config import ProjectConfig

    project_path = project_dir.resolve()

    if generate:
        _generate_expectation(project_path, generate, dict(a.split("=", 1) for a in arg))
        return

    config = ProjectConfig.load(project_path, target=target)
    project = Project(project_path)
    project.config = config

    adapter = get_adapter(config.warehouse, project_path=str(project.path))

    schema = SchemaYaml(project.path)
    gen = SchemaTestGenerator(schema)

    # Resolve which models to test
    if model:
        models_to_test = [model]
    elif select:
        from kelpmesh.core.graph import DAGBuilder
        from kelpmesh.core.executor import Executor
        from kelpmesh.state.engine import StateEngine
        state = StateEngine(project.path)
        ex = Executor(project, adapter, state)
        models_to_test = ex.dag.select_models(select=select)
        state.close()
    else:
        models_to_test = list(project.models.keys())

    schema_tests = []
    for m in models_to_test:
        schema_tests.extend(gen.tests_for_model(m))

    runner = TestRunner(adapter, schema_tests=schema_tests)
    tests_path = project.path / project.config.tests_path

    # Run SQL assertion tests
    if model:
        sql_results = runner.run_for_model(tests_path, model)
    else:
        sql_results = runner.run_all(tests_path)

    # Run YAML fixture tests
    fixture_runner = FixtureTestRunner(project)
    if model:
        fixture_results = fixture_runner.run_fixtures_for_model(tests_path, model)
    else:
        fixture_results = fixture_runner.run_all_fixtures(tests_path)

    results = sql_results + fixture_results

    table = Table(title="kelpmesh test results")
    table.add_column("Test", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Status", style="bold")
    table.add_column("Failures")

    passed = 0
    failed = 0
    warned = 0
    failed_details: list[dict] = []

    for r in results:
        is_warning = r.get("severity") == "warn" and not r["passed"]
        if is_warning:
            status = "[yellow]WARN[/yellow]"
            warned += 1
        else:
            status = "[green]PASS[/green]" if r["passed"] else "[red]FAIL[/red]"
        failures = str(r["failures"]) if r["failures"] else "0"
        test_type = r.get("type", "sql")
        sev = f" ({r.get('severity', 'error')})" if r.get("severity", "error") != "error" else ""
        table.add_row(r["name"] + sev, test_type, status, failures)
        if r["passed"]:
            passed += 1
        elif not is_warning:
            failed += 1
            failed_details.append(r)

    if results:
        console.print(table)
        parts = [f"{passed} passed"]
        if warned:
            parts.append(f"{warned} warned")
        if failed:
            parts.append(f"{failed} failed")
        console.print(f"\n[bold]Summary:[/bold] {', '.join(parts)}")
    else:
        console.print("[yellow]No tests found.[/yellow]")

    # Store failures in warehouse if requested
    if store_failures and failed_details:
        failures_table = f"{env}_test_failures" if env else "test_failures"
        try:
            adapter.execute(f"DROP TABLE IF EXISTS {failures_table}")
            adapter.execute(
                f"CREATE TABLE {failures_table} "
                f"(test_name VARCHAR, failures INTEGER, error VARCHAR)"
            )
            for r in failed_details:
                name_esc = r["name"].replace("'", "''")
                err_esc = (r.get("error") or "").replace("'", "''")
                adapter.execute(
                    f"INSERT INTO {failures_table} VALUES "
                    f"('{name_esc}', {r['failures']}, '{err_esc}')"
                )
            console.print(f"\n[dim]Failures stored in table: {failures_table}[/dim]")
        except Exception as e:
            console.print(f"\n[yellow]Could not store failures: {e}[/yellow]")

    adapter.disconnect()

    if failed > 0 and not warn:
        raise typer.Exit(1)


def _generate_expectation(project_path: Path, expectation: str, args: dict):
    pkgs_dir = _packages_dir(project_path)
    templates = []
    if pkgs_dir.exists():
        templates.extend(sorted(pkgs_dir.rglob("expectations/*.sql")))
    template = None
    for t in templates:
        if t.stem == expectation:
            template = t
            break
    if not template:
        console.print(f"[red]Expectation '{expectation}' not found. Available:[/red]")
        for t in templates:
            console.print(f"  - {t.stem}")
        raise typer.Exit(1)

    default_args = {
        "model": "ref('your_model')",
        "column": "column_name",
        "values": "'val1', 'val2'",
        "min_value": "0",
        "max_value": "100",
        "min_count": "1",
        "max_count": "999999",
    }
    default_args.update(args)

    sql = template.read_text(encoding="utf-8")

    description = ""
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("-- description:"):
            description = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("-- severity:"):
            default_args.setdefault("severity", stripped.split(":", 1)[1].strip())

    resolved = sql
    for key, val in default_args.items():
        resolved = resolved.replace("{{ " + key + " }}", val).replace("{{" + key + "}}", val)

    tests_dir = project_path / "tests"
    tests_dir.mkdir(exist_ok=True)

    default_args.pop("severity", None)
    model_part = default_args.get("model", "your_model").replace("ref('", "").replace("')", "")
    filename = f"{expectation}_{model_part}.sql"
    test_path = tests_dir / filename
    test_path.write_text(resolved, encoding="utf-8")
    console.print(f"[green]Generated test '{filename}' from expectation '{expectation}'[/green]")
    if description:
        console.print(f"  Description: {description}")
