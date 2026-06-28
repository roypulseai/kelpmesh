# kelpmesh-studio

Browser dashboard for [KelpMesh](https://github.com/saikatxtreme/kelpmesh) — the pure-SQL transformation platform.

## Installation

```bash
pip install kelpmesh-studio
```

This installs `kelpmesh-core` (the full CLI engine) plus the FastAPI + uvicorn dependencies needed to run the browser UI.

## Usage

```bash
# Start the browser dashboard (opens http://localhost:8501 automatically)
kelpmesh studio

# Core CLI still works exactly as before
kelpmesh run
kelpmesh plan
kelpmesh test
```

## What's included

`kelpmesh-studio` is a meta-package. It declares two groups of dependencies:

| Dependency | Purpose |
|-----------|---------|
| `kelpmesh-core>=0.2.0` | SQL engine, 9 adapters, 32 macros, security, scheduler, Dagster/Prefect |
| `fastapi>=0.110` | REST API for the browser dashboard |
| `uvicorn[standard]>=0.27` | ASGI server |
| `python-multipart>=0.0.6` | Form/file upload support |

## Just the CLI (no browser UI)

If you only need the CLI engine without the browser dashboard:

```bash
pip install kelpmesh-core
```

## License

Apache 2.0 · © 2026 Saikat Roy
