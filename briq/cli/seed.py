import typer
from pathlib import Path
from rich.console import Console
from briq.adapters import get_adapter
from briq.core.config import ProjectConfig
from briq.core.errors import sanitize_exception_message

console = Console()


def seed_cmd(
    seed_file: Path = typer.Argument(
        "seed.sql", help="Seed file (.sql / .csv / .tsv)", exists=True
    ),
    project_dir: Path = typer.Option(
        ".", "--project-dir", "-p", help="Project directory"
    ),
    table_name: str | None = typer.Option(
        None, "--table", "-t", help="Target table name (default: filename stem)"
    ),
):
    project_path = project_dir.resolve()
    config = ProjectConfig.load(project_path)
    adapter = get_adapter(config.warehouse, project_path=str(project_path))
    suffix = seed_file.suffix.lower()
    try:
        if suffix == ".sql":
            sql = seed_file.read_text(encoding="utf-8")
            adapter.execute(sql)
        elif suffix in (".csv", ".tsv"):
            name = table_name or seed_file.stem
            adapter.load_csv(
                path=str(seed_file.resolve()),
                table_name=name,
                delimiter="," if suffix == ".csv" else "\t",
            )
        else:
            console.print(f"[red]Unsupported seed format: {suffix}[/red]")
            raise typer.Exit(1)
        console.print(f"[green]Seed data loaded successfully as '{seed_file.stem}'.[/green]")
    except Exception as e:
        console.print(f"[red]Error seeding data: {sanitize_exception_message(str(e))}[/red]")
        adapter.disconnect()
        raise typer.Exit(1)
    adapter.disconnect()
