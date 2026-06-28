"""kelpmesh scan — secrets scanner for hardcoded credentials in SQL files."""

import logging
import os
import re
import sys
from pathlib import Path
from typing import List, Optional
import typer

_logger = logging.getLogger(__name__)

SCAN_PATTERNS: list[tuple[str, str]] = [
    # Passwords and secrets
    ("password", r"(?i)password\s*[=:]\s*['\"](?!['\"\s])[^'\"]{3,}['\"]"),
    ("secret_key", r"(?i)(secret|secret_key|secretkey)\s*[=:]\s*['\"](?!['\"\s])[^'\"]{4,}['\"]"),
    ("api_key", r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"](?!['\"\s])[^'\"]{8,}['\"]"),
    ("token", r"(?i)(token|auth_token|bearer)\s*[=:]\s*['\"](?!['\"\s])[^'\"]{8,}['\"]"),
    ("connection_string", r"(?i)(connection_string|conn_str|connstring)\s*[=:]\s*['\"][^'\"]+['\"]"),
    ("private_key", r"(?i)(private_key|privatekey|privkey)\s*[=:]\s*['\"][^'\"]+['\"]"),
    ("aws_key", r"(?i)(aws_access_key_id|aws_secret_access_key)\s*[=:]\s*['\"][^'\"]+['\"]"),
    ("pem_key", r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"),
    # Connection URLs with credentials
    ("jdbc_url", r"jdbc:[^'\"]+://[^:]+:[^@]+@"),
    ("postgres_url", r"postgres(ql)?://[^:]+:[^@]+@"),
    ("mysql_url", r"mysql://[^:]+:[^@]+@"),
    ("snowflake_url", r"snowflake://[^:]+:[^@]+@"),
    # Environment variable templates that shouldn't have hardcoded fallbacks
    ("env_fallback", r"env_var\(\s*['\"][^'\"]+['\"]\s*,\s*['\"](?![^'\"]*\{)[^'\"]{4,}['\"]\s*\)"),
]

IGNORE_COMMENT = re.compile(r"--\s*kelpmesh:scan-ignore\b")


def scan_file(
    path: Path, patterns: list[tuple[str, str]] | None = None
) -> list[dict]:
    results: list[dict] = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        _logger.debug("Could not read %s: %s", path, e)
        return results

    lines = content.split("\n")

    for lineno, line in enumerate(lines, 1):
        if IGNORE_COMMENT.search(line):
            continue
        stripped = line.strip()
        if stripped.startswith("#") or re.match(r"^--( |$)", stripped):
            continue
        for name, pattern in patterns or SCAN_PATTERNS:
            if re.search(pattern, line):
                results.append({
                    "file": str(path),
                    "line": lineno,
                    "type": name,
                    "content": line.strip()[:120],
                })

    return results


def scan_directory(
    directory: Path, extensions: set[str] | None = None,
) -> list[dict]:
    if extensions is None:
        extensions = {".sql", ".yml", ".yaml", ".py", ".cfg", ".ini", ".env.example"}
    results: list[dict] = []
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext in extensions:
                results.extend(scan_file(Path(root) / fname))
    return results


scan_app = typer.Typer(help="Security scanning utilities")


@scan_app.command(name="secrets")
def scan_secrets(
    path: Optional[str] = typer.Argument(
        None, help="File or directory to scan (default: models/)"
    ),
    all_files: bool = typer.Option(
        False, "--all", "-a", help="Scan all file types including YAML and config"
    ),
    fail: bool = typer.Option(
        False, "--fail", help="Exit with code 1 if secrets found"
    ),
):
    """Scan SQL files for hardcoded secrets and credentials."""
    base = Path.cwd()
    target = Path(path) if path else base / "models"
    if not target.is_absolute():
        target = base / target

    if not target.exists():
        typer.echo(f"Path not found: {target}")
        raise typer.Exit(1)

    extensions = {".sql", ".py"}
    if all_files:
        extensions.update({".yml", ".yaml", ".cfg", ".ini", ".env.example"})

    results: list[dict] = []
    if target.is_file():
        results = scan_file(target)
    else:
        results = scan_directory(target, extensions=extensions)

    if not results:
        typer.echo("[green]No secrets detected. ✓[/green]")
        return

    typer.echo(f"[yellow]Found {len(results)} potential secret(s):[/yellow]\n")
    for r in results:
        typer.echo(
            f"  {r['file']}:{r['line']}  "
            f"[red][{r['type']}][/red]  {r['content']}"
        )
    typer.echo(
        f"\n[yellow]Tip:[/yellow] Use environment variables or "
        f"kelpmesh.yml for secrets. Mark false positives with "
        f"[bold]-- kelpmesh:scan-ignore[/bold] comment."
    )

    if fail:
        raise typer.Exit(1)


@scan_app.command(name="generate-key")
def generate_key():
    """Generate a random encryption key for KELPMESH_ENCRYPTION_KEY."""
    try:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        typer.echo(f"Encryption key:\n  {key}")
        typer.echo("\nSet it as an environment variable:")
        typer.echo(f"  export KELPMESH_ENCRYPTION_KEY={key}  # Linux/macOS")
        typer.echo(f'  set KELPMESH_ENCRYPTION_KEY={key}    # Windows cmd')
        typer.echo(f'  $env:KELPMESH_ENCRYPTION_KEY="{key}" # PowerShell')
    except ImportError:
        typer.echo("Install cryptography: pip install kelpmesh[studio]")
        raise typer.Exit(1)
