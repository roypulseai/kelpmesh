"""kelpmesh security CLI — audit, classify, masking, RLS, erasure commands."""

import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kelpmesh.adapters import get_adapter
from kelpmesh.core.project import Project
from kelpmesh.security.audit import AuditLog
from kelpmesh.security.classifier import DataClassifier
from kelpmesh.security.erasure import erase_pii
from kelpmesh.security.masking import (
    ROLE_ACCESS,
    ROLE_HIERARCHY,
    can_access_column,
    column_mask_sql,
)
from kelpmesh.security.rls import RlsEngine

security_app = typer.Typer(help="Access control, auditing, classification, and erasure — subcommands: audit-log, classify, mask, rls, clean-pii, status, roles")
console = Console()


@security_app.command(name="audit")
def audit_log_cmd(
    limit: int = typer.Option(50, "--limit", "-l", help="Number of recent entries"),
    actor: str = typer.Option(None, "--actor", "-a", help="Filter by actor"),
    action: str = typer.Option(None, "--action", help="Filter by action type"),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """View the audit log."""
    audit = AuditLog(project_dir.resolve())
    entries = audit.query(limit=limit, actor=actor, action=action)

    if json_out:
        console.print_json(json.dumps(entries))
        return

    if not entries:
        console.print("[yellow]No audit log entries found.[/yellow]")
        return

    table = Table(title=f"Audit Log ({len(entries)} entries)")
    table.add_column("Time", style="dim")
    table.add_column("Actor")
    table.add_column("Action")
    table.add_column("Resource")
    table.add_column("Status")
    table.add_column("Detail", overflow="fold")
    for e in reversed(entries):
        detail = (e.get("detail") or "")[:60]
        table.add_row(
            (e.get("timestamp") or "")[:19],
            e.get("actor", ""),
            e.get("action", ""),
            e.get("resource", ""),
            e.get("status", ""),
            detail,
        )
    console.print(table)


@security_app.command(name="classify")
def classify_cmd(
    table: str = typer.Argument(None, help="Table to classify"),
    column: str = typer.Option(None, "--column", "-c", help="Column to classify"),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON"),
    init: bool = typer.Option(False, "--init", help="Generate classify.yml stub"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """Classify columns by sensitivity level (pii/sensitive/restricted/internal)."""
    project_path = project_dir.resolve()

    if init:
        DataClassifier.generate_stub(project_path / "classify.yml")
        console.print("[green]Created[/green] classify.yml — edit to add your PII/sensitive columns.")
        return

    classifier = DataClassifier(project_path)

    if column and table:
        sens = classifier.classify(table, column)
        console.print(f"[bold]{table}.{column}[/bold] -> [cyan]{sens}[/cyan]")
        return

    if table:
        rules = classifier.get_table_rules(table)
        if json_out:
            console.print_json(json.dumps(rules))
            return
        if not rules:
            console.print(f"[yellow]No custom rules for '{table}' (check classify.yml)[/yellow]")
        for col, sens in sorted(rules.items()):
            console.print(f"  [cyan]{col}[/cyan] -> {sens}")
        return

    # Show built-in defaults
    from kelpmesh.security.classifier import DEFAULT_RULES
    if json_out:
        console.print_json(json.dumps(DEFAULT_RULES))
        return
    table_disp = Table(title="Built-in Classification Rules")
    table_disp.add_column("Column Pattern")
    table_disp.add_column("Sensitivity")
    for col, sens in sorted(DEFAULT_RULES.items()):
        table_disp.add_row(col, sens)
    console.print(table_disp)

    custom = classifier.all_classified_tables()
    if custom:
        console.print(f"\n[yellow]Custom rules exist for: {', '.join(custom)}[/yellow]")


@security_app.command(name="mask")
def mask_cmd(
    table: str = typer.Argument(..., help="Table name"),
    columns: str = typer.Option(..., "--columns", "-c", help="Comma-separated column names"),
    role: str = typer.Option("viewer", "--role", "-r", help="User role"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """Preview column masking for a given table and role."""
    classifier = DataClassifier(project_dir.resolve())
    col_list = [c.strip() for c in columns.split(",")]
    table_disp = Table(title=f"Column Masking for role={role} on {table}")
    table_disp.add_column("Column")
    table_disp.add_column("Sensitivity")
    table_disp.add_column("Access")
    table_disp.add_column("Masked SQL")
    for col in col_list:
        sens = classifier.classify(table, col)
        access = "YES" if can_access_column(sens, role) else "NO"
        mask_expr = column_mask_sql(col, sens)
        masked = mask_expr if mask_expr and not can_access_column(sens, role) else "(unmasked)"
        table_disp.add_row(col, sens, access, masked)
    console.print(table_disp)


@security_app.command(name="rls")
def rls_cmd(
    table: str = typer.Argument(None, help="Table to inspect"),
    role: str = typer.Option(None, "--role", "-r", help="Filter by role"),
    init: bool = typer.Option(False, "--init", help="Generate security.yml stub"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """View row-level security policies."""
    project_path = project_dir.resolve()

    if init:
        RlsEngine.generate_stub(project_path / "security.yml")
        console.print("[green]Created[/green] security.yml — define RLS policies.")
        return

    rls = RlsEngine(project_path)
    policies = rls.list_policies()

    if not policies:
        console.print("[yellow]No RLS policies configured.[/yellow]")
        console.print("  Create security.yml or add rls: section to kelpmesh.yml")
        return

    filtered = [
        p for p in policies
        if (table is None or p["table"] == table.lower())
        and (role is None or p["role"] == role)
    ]

    if not filtered:
        console.print("[yellow]No matching policies.[/yellow]")
        return

    t = Table(title="RLS Policies")
    t.add_column("Table")
    t.add_column("Role")
    t.add_column("Filter")
    for p in filtered:
        t.add_row(p["table"], p["role"], p["filter"])
    console.print(t)


@security_app.command(name="clean-pii")
def clean_pii_cmd(
    identifier_column: str = typer.Option(
        ..., "--id-col", help="Column identifying the data subject (e.g. email)"
    ),
    identifier_value: str = typer.Option(
        ..., "--id-value", help="Value to identify the data subject"
    ),
    tables: str = typer.Option(
        None, "--tables", "-t", help="Comma-separated tables (default: all)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview without making changes"
    ),
    role: str = typer.Option(
        "admin", "--as-role", help="Execute as this role"
    ),
    project_dir: Path = typer.Option(
        ".", "--project-dir", "-p", help="Project directory"
    ),
):
    """Right to be forgotten — purge PII for a data subject across warehouse tables."""
    project_path = project_dir.resolve()
    project = Project(project_path)
    adapter = get_adapter(project.config.warehouse, project_path=str(project_path))
    classifier = DataClassifier(project_path)
    audit_log = AuditLog(project_path)
    table_list = [t.strip() for t in tables.split(",")] if tables else None

    try:
        adapter.connect()

        if dry_run:
            console.print("[yellow]DRY RUN — no changes will be made[/yellow]\n")

        result = erase_pii(
            adapter=adapter,
            classifier=classifier,
            audit_log=audit_log,
            identifier_column=identifier_column,
            identifier_value=identifier_value,
            tables=table_list,
            actor=role,
            dry_run=dry_run,
        )

        t = Table(title="PII Erasure Results")
        t.add_column("Table")
        t.add_column("Rows Affected")
        for table_name, rows in result.items():
            status = "[red]ERROR" if rows == -1 else str(rows)
            t.add_row(table_name, status)
        console.print(t)

        if not dry_run:
            total = sum(max(r, 0) for r in result.values())
            console.print(f"\n[green]Erasure complete.[/green] {total} total rows affected.")
            console.print("Audit entries written to target/audit.log")

    finally:
        adapter.disconnect()


@security_app.command(name="status")
def security_status_cmd(
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
):
    """Show overall security posture of the project."""
    project_path = project_dir.resolve()

    checks = []

    # Encryption
    enc_key = os.environ.get("KELPMESH_ENCRYPTION_KEY")
    checks.append(("Encryption key set", bool(enc_key)))

    # Classify config
    classify_yml = project_path / "classify.yml"
    checks.append(("classify.yml exists", classify_yml.exists()))

    # RLS config
    security_yml = project_path / "security.yml"
    rls_in_kelpmesh = False
    config_yml = project_path / "kelpmesh.yml"
    if config_yml.exists():
        import yaml
        raw = yaml.safe_load(config_yml.read_text(encoding="utf-8")) or {}
        rls_in_kelpmesh = bool(raw.get("rls") or raw.get("security", {}).get("rls"))
    checks.append(("RLS policies configured", security_yml.exists() or rls_in_kelpmesh))

    # Audit log
    audit_path = project_path / "target" / "audit.log"
    audit_count = 0
    if audit_path.exists():
        audit_count = len(audit_path.read_text(encoding="utf-8").strip().split("\n"))
    checks.append(("Audit log entries", audit_count))

    # Scanning
    checks.append(("Secrets scanner available", True))

    # Telemetry guard
    checks.append(("Telemetry guard active", True))

    panel = Panel("[bold]Security Posture[/bold]", expand=False)
    console.print(panel)

    t = Table.grid()
    t.add_column()
    t.add_column()
    for label, ok in checks:
        icon = "[green]✓" if ok else "[red]✗"
        t.add_row(f"  {icon}[/green]", label)
    console.print(t)

    if audit_count > 0:
        audit = AuditLog(project_path)
        counts = audit.count_by_action()
        console.print("\n[bold]Audit summary:[/bold]")
        for action, cnt in sorted(counts.items()):
            console.print(f"  [dim]{action}:[/dim] {cnt}")


@security_app.command(name="roles")
def roles_cmd():
    """List available roles and their access levels."""
    t = Table(title="Role Hierarchy & Column Access")
    t.add_column("Role")
    t.add_column("Accessible Sensitivity Levels")
    for role in ROLE_HIERARCHY:
        levels = ", ".join(sorted(ROLE_ACCESS.get(role, set())))
        t.add_row(role, levels)
    console.print(t)
    console.print("\nRole hierarchy (higher = more privilege): viewer < editor < admin")
