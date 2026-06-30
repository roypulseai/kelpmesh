"""kelpmesh license — generate Studio license keys (requires private key)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def license_cmd(
    tier: str = typer.Argument(..., help="Tier: pro, business, enterprise"),
    email: str = typer.Option("", "--email", "-e", help="Customer email"),
    seats: int = typer.Option(1, "--seats", "-s", help="Number of seats"),
    days: int = typer.Option(365, "--days", "-d", help="Validity in days"),
    key_file: Path = typer.Option(
        None,
        "--key-file",
        "-k",
        help="Path to Ed25519 private key PEM file (defaults to KELPMESH_STUDIO_PRIVATE_KEY env)",
    ),
):
    """Generate a KelpMesh Studio license key.

    Requires the Ed25519 private key (NOT in the repo). Provide it via:
      --key-file /path/to/private_key.pem
      or KELPMESH_STUDIO_PRIVATE_KEY env var (PEM string)
      or KELPMESH_STUDIO_PRIVATE_KEY_FILE env var (path to PEM file)

    Examples:

        kelpmesh license pro --email customer@example.com --seats 5 --days 365

        kelpmesh license business --email team@corp.com -k /secure/private_key.pem
    """
    from kelpmesh_studio.licensing import generate_license_key, TIER_DEFS

    if tier not in TIER_DEFS:
        console.print(f"[red]Unknown tier: {tier}. Valid: {', '.join(TIER_DEFS.keys())}[/red]")
        raise typer.Exit(1)

    # Load private key from file or env
    pem_data = None
    if key_file and key_file.exists():
        pem_data = key_file.read_text()
    elif key_file:
        console.print(f"[red]Key file not found: {key_file}[/red]")
        raise typer.Exit(1)

    expires_at = datetime.now(timezone.utc) + timedelta(days=days)

    try:
        key = generate_license_key(
            tier=tier,
            email=email,
            seats=seats,
            expires_at=expires_at,
            private_key_pem=pem_data,
        )
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold green]License key generated:[/bold green]")
    console.print(f"  [cyan]{key}[/cyan]\n")
    console.print(f"[dim]Tier: {tier}  Seats: {seats}  Expires: {expires_at.date().isoformat()}  Email: {email or '(none)'}[/dim]")
    console.print(f"[dim]Activate: export KELPMESH_STUDIO_LICENSE_KEY='{key}'[/dim]")
