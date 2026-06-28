import typer
from pathlib import Path
from rich.console import Console
from briq.core.config import ProjectConfig

console = Console()

INIT_TEMPLATES = {
    "models/example_model.sql": """-- Example briq model
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
    "briq.yml": """name: my_briq_project
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
    "README.md": """# My briq Project

This is a briq data transformation project.

## Getting started

```bash
pip install briq
briq run
briq test
briq docs --serve
```
""",
}


def init_cmd(
    name: str = typer.Argument("briq_project", help="Project name"),
    project_dir: Path = typer.Option(
        ".", "--project-dir", "-p", help="Project directory"
    ),
    encrypt: bool = typer.Option(False, "--encrypt", help="Enable state DB encryption with AES-256-GCM"),
):
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

    console.print(f"\n[bold]briq project initialized at:[/bold] {base_dir}")
    if encrypt:
        try:
            from cryptography.fernet import Fernet
            key = Fernet.generate_key().decode()
            env_line = f'BRIQ_ENCRYPTION_KEY={key}'
            env_file = base_dir / ".env"
            if not env_file.exists():
                env_file.write_text(f"# Briq encryption key (AES-256-GCM)\n{env_line}\n", encoding="utf-8")
                console.print(f"  [green]Created[/green] .env (with encryption key)")
            env_path = base_dir / "briq.yml"
            if env_path.exists():
                content = env_path.read_text(encoding="utf-8")
                if "encryption_key" not in content:
                    content = content.replace("threads: 4", "threads: 4\n  encryption_key: ${BRIQ_ENCRYPTION_KEY}")
                    env_path.write_text(content, encoding="utf-8")
                    console.print(f"  [green]Updated[/green] briq.yml (encryption key reference)")
            console.print(f"\n[yellow]Encryption enabled.[/yellow] State DB will be encrypted with AES-256-GCM.")
            console.print(f"  [dim]Key: {key[:8]}...{key[-4:]}[/dim]")
            console.print(f"  [dim]Set BRIQ_ENCRYPTION_KEY in your shell or .env file[/dim]")
        except ImportError:
            console.print("[yellow]Warning: cryptography package not available.[/yellow]")
            console.print("[yellow]Install: pip install briq[studio][/yellow]")

    console.print("\nNext steps:")
    console.print("  1. Add your SQL models to the [cyan]models/[/cyan] directory")
    console.print("  2. Run [cyan]briq run[/cyan] to execute all models")
    console.print("  3. Run [cyan]briq test[/cyan] to run tests")
    console.print("  4. Run [cyan]briq docs --serve[/cyan] to view documentation")
