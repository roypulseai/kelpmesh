"""kelpmesh mesh — cross-project mesh commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()
err_console = Console(stderr=True)

mesh_app = typer.Typer(
    name="mesh",
    help="Manage cross-project references, access control, and contracts.",
    no_args_is_help=True,
)


def _load_mesh(workspace: Path):
    from kelpmesh.mesh.config import MeshConfig
    cfg = MeshConfig.load(workspace)
    if cfg.is_empty():
        err_console.print(
            "[red]No mesh.yml found.[/red] Create one with [bold]kelpmesh mesh init[/bold]."
        )
        raise typer.Exit(1)
    return cfg


# ---------------------------------------------------------------------------
# mesh init
# ---------------------------------------------------------------------------

@mesh_app.command("init")
def mesh_init(
    name: str = typer.Option("my_mesh", "--name", "-n", help="Mesh name"),
    workspace: Path = typer.Option(Path("."), "--workspace", help="Workspace root"),
):
    """Scaffold a mesh.yml in the current workspace."""
    from kelpmesh.mesh.config import MeshConfig, MeshProject
    out = workspace.resolve()
    dest = out / "mesh.yml"
    if dest.exists():
        err_console.print("[yellow]mesh.yml already exists.[/yellow]")
        raise typer.Exit(0)
    cfg = MeshConfig(
        name=name,
        projects=[
            MeshProject(name="project_a", path=Path("./project_a"), warehouse="duckdb"),
            MeshProject(name="project_b", path=Path("./project_b"), warehouse="duckdb"),
        ],
        workspace_root=out,
    )
    cfg.write(out)
    console.print(f"[green]✓[/green] Created [bold]{dest}[/bold]")
    console.print("Edit it to list your real projects, then run [bold]kelpmesh mesh status[/bold].")


# ---------------------------------------------------------------------------
# mesh status
# ---------------------------------------------------------------------------

@mesh_app.command("status")
def mesh_status(
    workspace: Path = typer.Option(Path("."), "--workspace", help="Workspace root"),
):
    """Show health of all projects in the mesh."""
    from kelpmesh.mesh.health import MeshHealthChecker

    cfg = _load_mesh(workspace.resolve())
    checker = MeshHealthChecker(cfg)
    report = checker.check()

    console.print(f"\n[bold]Mesh:[/bold] {report.mesh_name}  "
                  f"[dim]({report.project_count} projects)[/dim]\n")

    tbl = Table(show_header=True, header_style="bold")
    tbl.add_column("Project", style="cyan")
    tbl.add_column("Status")
    tbl.add_column("Path")
    tbl.add_column("Interface")
    tbl.add_column("Issues", justify="right")

    for ph in report.project_health:
        status_str = {
            "healthy": "[green]● healthy[/green]",
            "warn":    "[yellow]▲ warn[/yellow]",
            "error":   "[red]✗ error[/red]",
            "missing": "[red]✗ missing[/red]",
        }.get(ph.status, ph.status)

        proj = cfg.get_project(ph.name)
        proj_path = proj.resolve_path(workspace.resolve()) if proj else Path("?")
        interface_str = "[green]✓[/green]" if ph.has_interface else "[dim]—[/dim]"
        issue_count = (
            len(ph.access_violations)
            + len(ph.contract_violations)
            + len(ph.missing_ref_errors)
        )
        tbl.add_row(
            ph.name,
            status_str,
            str(proj_path),
            interface_str,
            str(issue_count) if issue_count else "[dim]0[/dim]",
        )

    console.print(tbl)

    if report.all_healthy:
        console.print("[green]All projects healthy.[/green]")
    else:
        console.print(
            f"[yellow]{report.total_issues} issue(s) found.[/yellow] "
            "Run [bold]kelpmesh mesh validate[/bold] for details."
        )


# ---------------------------------------------------------------------------
# mesh validate
# ---------------------------------------------------------------------------

@mesh_app.command("validate")
def mesh_validate(
    workspace: Path = typer.Option(Path("."), "--workspace", help="Workspace root"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Validate a single project"),
):
    """Validate cross-project refs, access policies, and producer contracts."""
    from kelpmesh.mesh.health import MeshHealthChecker

    cfg = _load_mesh(workspace.resolve())
    checker = MeshHealthChecker(cfg)

    if project:
        health_list = [checker.check_project(project)]
        if health_list[0] is None:
            err_console.print(f"[red]Project '{project}' not in mesh.yml[/red]")
            raise typer.Exit(1)
    else:
        report = checker.check()
        health_list = report.project_health

    issues_found = False
    for ph in health_list:
        if not ph.path_exists:
            console.print(f"[red]✗ {ph.name}[/red] — path does not exist")
            issues_found = True
            continue

        all_issues = (
            [{"kind": "missing_ref", **e} for e in ph.missing_ref_errors]
            + [{"kind": "access", **e} for e in ph.access_violations]
            + [{"kind": v.kind, "ref": v.model, "detail": v.detail} for v in ph.contract_violations]
        )
        if all_issues:
            issues_found = True
            console.print(f"\n[bold red]{ph.name}[/bold red] — {len(all_issues)} issue(s)")
            for issue in all_issues:
                kind = issue.get("kind", "")
                detail = issue.get("detail") or issue.get("reason") or issue.get("error", "")
                ref = issue.get("ref", "")
                console.print(f"  [red]•[/red] [{kind}] {ref}: {detail}")
        else:
            console.print(f"[green]✓[/green] {ph.name} — no issues")

    if issues_found:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# mesh graph
# ---------------------------------------------------------------------------

@mesh_app.command("graph")
def mesh_graph(
    workspace: Path = typer.Option(Path("."), "--workspace", help="Workspace root"),
):
    """Print the cross-project dependency graph."""
    from kelpmesh.mesh.health import MeshHealthChecker

    cfg = _load_mesh(workspace.resolve())
    checker = MeshHealthChecker(cfg)
    graph = checker.cross_project_graph()

    console.print(f"\n[bold]Cross-project dependency graph[/bold] — {cfg.name}\n")
    for proj, deps in graph.items():
        if deps:
            dep_str = ", ".join(f"[cyan]{d}[/cyan]" for d in deps)
            console.print(f"  [bold]{proj}[/bold] → {dep_str}")
        else:
            console.print(f"  [bold]{proj}[/bold] [dim](no cross-project refs)[/dim]")


# ---------------------------------------------------------------------------
# mesh publish
# ---------------------------------------------------------------------------

@mesh_app.command("publish")
def mesh_publish(
    project_dir: Path = typer.Option(Path("."), "--project-dir", help="Project to publish from"),
    project_name: str = typer.Option("", "--name", help="Override project name"),
    workspace: Path = typer.Option(Path("."), "--workspace", help="Workspace root"),
):
    """Generate or update interface.yml from this project's public models in schema.yml."""
    import datetime

    from kelpmesh.mesh.access import AccessChecker
    from kelpmesh.mesh.contracts import InterfaceColumn, InterfaceModel, ProducerContract

    proj_path = project_dir.resolve()
    name = project_name or proj_path.name

    checker = AccessChecker(proj_path)
    public_models = checker.list_public_models()

    if not public_models:
        console.print("[yellow]No public models found in schema.yml. "
                      "Add [bold]access: public[/bold] to models you want to expose.[/yellow]")
        raise typer.Exit(0)

    # Build contract from schema.yml
    import yaml
    schema_data: dict[str, dict] = {}
    for fname in ("schema.yml", "schema.yaml", "models/schema.yml", "models/schema.yaml"):
        p = proj_path / fname
        if p.exists():
            raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            for m in raw.get("models", []):
                schema_data[m["name"]] = m
            break

    interface_models = []
    for model_name in public_models:
        m_data = schema_data.get(model_name, {})
        cols = [
            InterfaceColumn(
                name=c["name"],
                data_type=c.get("data_type", "unknown"),
                description=c.get("description", ""),
                required=not c.get("nullable", False),
            )
            for c in m_data.get("columns", [])
        ]
        existing = ProducerContract.load(proj_path)
        existing_model = existing.get_model(model_name) if existing else None
        version = (existing_model.version + 1) if existing_model else 1

        interface_models.append(InterfaceModel(
            name=model_name,
            access="public",
            version=version,
            columns=cols,
            description=m_data.get("description", ""),
        ))

    contract = ProducerContract(
        project=name,
        version=1,
        published_at=datetime.date.today().isoformat(),
        models=interface_models,
    )
    contract.write(proj_path)
    console.print(f"[green]✓[/green] Published interface.yml with {len(interface_models)} public model(s):")
    for m in interface_models:
        console.print(f"  • [cyan]{m.name}[/cyan] v{m.version} ({len(m.columns)} column(s))")
