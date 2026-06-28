import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from briq.core.project import Project
from briq.core.schema_yaml import SchemaYaml
from briq.testing.runner import TestRunner
from briq.testing.schema_tests import SchemaTestGenerator
from briq.adapters import get_adapter
from briq.core.packages import _packages_dir

console = Console()


def test_cmd(
    model: str = typer.Argument(None, help="Model name to test"),
    project_dir: Path = typer.Option(
        ".", "--project-dir", "-p", help="Project directory"
    ),
    warn: bool = typer.Option(False, "--warn", "-w", help="Treat warnings as non-fatal"),
    generate: str = typer.Option(None, "--generate", "-g", help="Generate test from expectation (not_null, unique, etc.)"),
    arg: list[str] = typer.Option([], "--arg", "-a", help="Template arguments (key=value)"),
):
    project_path = project_dir.resolve()

    if generate:
        _generate_expectation(project_path, generate, dict(a.split("=", 1) for a in arg))
        return

    project = Project(project_path)
    adapter = get_adapter(project.config.warehouse, project_path=str(project.path))

    schema = SchemaYaml(project.path)
    gen = SchemaTestGenerator(schema)
    if model:
        schema_tests = gen.tests_for_model(model)
    else:
        schema_tests = gen.all_tests(list(project.models.keys()))
    runner = TestRunner(adapter, schema_tests=schema_tests)

    tests_path = project.path / project.config.tests_path

    if model:
        results = runner.run_for_model(tests_path, model)
    else:
        results = runner.run_all(tests_path)

    table = Table(title="briq test results")
    table.add_column("Test", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Failures")

    passed = 0
    failed = 0
    warned = 0

    for r in results:
        is_warning = r.get("severity") == "warn" and not r["passed"]
        if is_warning:
            status = "[yellow]WARN[/yellow]"
            warned += 1
        else:
            status = "[green]PASS[/green]" if r["passed"] else "[red]FAIL[/red]"
        failures = str(r["failures"]) if r["failures"] else "0"
        sev = f" ({r.get('severity', 'error')})" if r.get("severity", "error") != "error" else ""
        table.add_row(r["name"] + sev, status, failures)
        if r["passed"]:
            passed += 1
        elif not is_warning:
            failed += 1

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
