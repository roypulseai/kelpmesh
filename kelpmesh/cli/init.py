from pathlib import Path

import typer
from rich.console import Console

console = Console()

INIT_TEMPLATES = {
    "models/example_model.sql": """-- Example kelpmesh model
-- This model demonstrates a simple transformation

SELECT
    1 AS id,
    'hello' AS greeting
""",
    "tests/example_model.sql": """-- Test: example_model should have data
SELECT COUNT(*) AS failures
FROM example_model
WHERE id IS NULL
""",
    "kelpmesh.yml": """name: my_kelpmesh_project
models_path: models
tests_path: tests
target_path: target
warehouse:
  type: duckdb
  threads: 4
""",
    ".gitignore": """target/
*.duckdb
*.pyc
__pycache__/
.env
""",
    "README.md": """# My kelpmesh Project

This is a kelpmesh data transformation project.

## Getting started

```bash
pip install kelpmesh
kelpmesh run
kelpmesh test
kelpmesh docs --serve
```
""",
}


def init_cmd(
    name: str = typer.Argument("kelpmesh_project", help="Project name"),
    project_dir: Path = typer.Option(
        ".", "--project-dir", "-p", help="Project directory"
    ),
    encrypt: bool = typer.Option(False, "--encrypt", help="Enable state DB encryption with AES-256-GCM"),
):
    """Scaffold a new kelpmesh project with starter files and directories."""
    base_dir = project_dir.resolve()
    models_dir = base_dir / "models"
    tests_dir = base_dir / "tests"
    target_dir = base_dir / "target"

    models_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, content in INIT_TEMPLATES.items():
        full_path = base_dir / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if not full_path.exists():
            full_path.write_text(content, encoding="utf-8")
            console.print(f"  [green]Created[/green] {rel_path}")
        else:
            console.print(f"  [yellow]Skipped[/yellow] {rel_path} (already exists)")

    console.print(f"\n[bold]kelpmesh project initialized at:[/bold] {base_dir}")
    if encrypt:
        try:
            from cryptography.fernet import Fernet
            key = Fernet.generate_key().decode()
            env_line = f'KELPMESH_ENCRYPTION_KEY={key}'
            env_file = base_dir / ".env"
            if not env_file.exists():
                env_file.write_text(f"# KelpMesh encryption key (AES-256-GCM)\n{env_line}\n", encoding="utf-8")
                console.print("  [green]Created[/green] .env (with encryption key)")
            env_path = base_dir / "kelpmesh.yml"
            if env_path.exists():
                content = env_path.read_text(encoding="utf-8")
                if "encryption_key" not in content:
                    content = content.replace("threads: 4", "threads: 4\n  encryption_key: ${KELPMESH_ENCRYPTION_KEY}")
                    env_path.write_text(content, encoding="utf-8")
                    console.print("  [green]Updated[/green] kelpmesh.yml (encryption key reference)")
            console.print("\n[yellow]Encryption enabled.[/yellow] State DB will be encrypted with AES-256-GCM.")
            console.print(f"  [dim]Key: {key[:8]}...{key[-4:]}[/dim]")
            console.print("  [dim]Set KELPMESH_ENCRYPTION_KEY in your shell or .env file[/dim]")
        except ImportError:
            console.print("[yellow]Warning: cryptography package not available.[/yellow]")
            console.print("[yellow]Install: pip install kelpmesh[studio][/yellow]")

    console.print("\nNext steps:")
    console.print("  1. Add your SQL models to the [cyan]models/[/cyan] directory")
    console.print("  2. Run [cyan]kelpmesh run[/cyan] to execute all models")
    console.print("  3. Run [cyan]kelpmesh test[/cyan] to run tests")
    console.print("  4. Run [cyan]kelpmesh docs --serve[/cyan] to view documentation")
