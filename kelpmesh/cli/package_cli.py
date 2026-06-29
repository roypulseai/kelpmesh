import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from kelpmesh.core.packages import create_package, search_packages, package_info

console = Console()
package_app = typer.Typer(help="Manage kelpmesh packages")


@package_app.command(name="init")
def package_init(
    name: str = typer.Argument(..., help="Package name"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """Create a new kelpmesh package scaffold."""
    pkg_dir = create_package(project_dir.resolve(), name)
    console.print(f"[green]Created package '{name}' at {pkg_dir}[/green]")


@package_app.command(name="search")
def package_search(
    query: str = typer.Argument("", help="Search query"),
):
    """Search the kelpmesh package registry for available packages."""
    results = search_packages(query)
    if not results:
        console.print("[yellow]No packages found[/yellow]")
        return
    table = Table(title="Available packages")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="bold")
    table.add_column("Version", style="bold")
    for pkg in results:
        table.add_row(pkg["name"], pkg["description"], pkg["version"])
    console.print(table)


@package_app.command(name="info")
def package_info_cmd(
    name: str = typer.Argument(..., help="Package name"),
):
    """Show information about a specific package from the registry."""
    info = package_info(name)
    if info:
        console.print(f"[bold cyan]{info['name']}[/bold cyan]")
        console.print(f"  Description: {info['description']}")
        console.print(f"  Version: {info['version']}")
        console.print(f"  Source: {info['source']}")
    else:
        console.print(f"[red]Package '{name}' not found in registry[/red]")


@package_app.command(name="list")
def package_list(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """List installed packages in the current project."""
    from kelpmesh.core.packages import list_packages
    packages = list_packages(project_dir.resolve())
    if not packages:
        console.print("[yellow]No packages installed[/yellow]")
        return
    table = Table(title="Installed packages")
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="bold")
    table.add_column("Version", style="bold")
    for pkg in packages:
        table.add_row(pkg["name"], pkg["source"], pkg.get("version", "-"))
    console.print(table)
