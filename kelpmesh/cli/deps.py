import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from kelpmesh.core.packages import (
    add_package, remove_package, list_packages, install_packages,
    search_packages, package_info,
)

console = Console()


def deps_cmd(
    action: str = typer.Argument(..., help="add, remove, install, list, search, info"),
    package_name: str = typer.Argument(None, help="Package name"),
    source: str = typer.Option(None, "--source", "-s", help="Package source (path, git URL, or registry name)"),
    version: str = typer.Option(None, "--version", "-v", help="Package version"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    query: str = typer.Option("", "--query", "-q", help="Search query"),
):
    """Manage project dependencies — add, remove, install, or list packages."""
    project_path = project_dir.resolve()

    if action == "add":
        if not package_name:
            console.print("[red]Usage: kelpmesh deps add <package> [--source <path>] [--version <ver>][/red]")
            raise typer.Exit(1)
        info = package_info(package_name)
        if info and not source:
            source = info["name"]
        add_package(project_path, package_name, source, version)
        console.print(f"[green]Added package '{package_name}' to kelpmesh.lock[/green]")
        console.print("Run [bold]kelpmesh deps install[/bold] to install.")

    elif action == "remove":
        if not package_name:
            console.print("[red]Usage: kelpmesh deps remove <package>[/red]")
            raise typer.Exit(1)
        remove_package(project_path, package_name)
        console.print(f"[green]Removed package '{package_name}'[/green]")

    elif action == "install":
        install_packages(project_path)
        packages = list_packages(project_path)
        installed = [p for p in packages if p["installed"]]
        console.print(f"[green]Installed {len(installed)} package(s):[/green]")
        for pkg in installed:
            ver = f" v{pkg.get('version', '?')}" if "version" in pkg else ""
            console.print(f"  - {pkg['name']}{ver}")

    elif action == "list":
        packages = list_packages(project_path)
        if not packages:
            console.print("[yellow]No packages in kelpmesh.lock[/yellow]")
            return
        table = Table(title="kelpmesh packages")
        table.add_column("Name", style="cyan")
        table.add_column("Source", style="bold")
        table.add_column("Version", style="bold")
        table.add_column("Installed", style="bold")
        for pkg in packages:
            installed = "[green]yes[/green]" if pkg["installed"] else "[red]no[/red]"
            table.add_row(pkg["name"], pkg["source"], pkg.get("version", "-"), installed)
        console.print(table)

    elif action == "search":
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

    elif action == "info":
        if not package_name:
            console.print("[red]Usage: kelpmesh deps info <package>[/red]")
            raise typer.Exit(1)
        info = package_info(package_name)
        if info:
            console.print(f"[bold cyan]{info['name']}[/bold cyan]")
            console.print(f"  Description: {info['description']}")
            console.print(f"  Version: {info['version']}")
            console.print(f"  Source: {info['source']}")
        else:
            console.print(f"[red]Package '{package_name}' not found in registry[/red]")

    else:
        console.print(f"[red]Unknown action: {action}. Use add, remove, install, list, search, or info.[/red]")
        raise typer.Exit(1)
