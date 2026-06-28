# Core Commands

## kelpmesh init

Scaffold a new KelpMesh project.

```bash
kelpmesh init [project_name] [options]
```

Options:
- `--encrypt` — Initialize with state encryption support

## kelpmesh run

Execute models in dependency order.

```bash
kelpmesh run [options]
```

Options:
- `--select` — Model selection expression (`+model`, `model+`, `@model`)
- `--full-refresh` — Re-run all models regardless of state
- `--threads` — Number of parallel threads (default: 4)

## kelpmesh test

Run SQL assertion tests.

```bash
kelpmesh test [options]
```

Options:
- `--warn` — Treat test failures as warnings (non-blocking)
- `--select` — Test selection expression

## kelpmesh build

Run models then tests in a single command.

```bash
kelpmesh build [options]
```

## kelpmesh diff

Compare current model output against the previous run.

```bash
kelpmesh diff <model_name>
```

## kelpmesh preview

Preview model data from the warehouse.

```bash
kelpmesh preview <model_name> [options]
```

Options:
- `--limit` — Number of rows to show (default: 100)

## kelpmesh docs

Generate static HTML documentation for your project.

```bash
kelpmesh docs [options]
```

Options:
- `--serve` — Serve docs with a local HTTP server
- `--port` — Port for HTTP server (default: 8000)

## kelpmesh ls

List models with their status and materialization type.

```bash
kelpmesh ls [options]
```

## kelpmesh clean

Remove target/ directory and reset project state.

```bash
kelpmesh clean
```

## kelpmesh seed

Load seed SQL data into the warehouse.

```bash
kelpmesh seed <seed_file.sql>
```

## KelpMesh schema diff

Detect schema drift by comparing current warehouse schema against stored schema.

```bash
KelpMesh schema diff
```

## kelpmesh debug

Show project health summary including encryption status, warehouse connection, and security posture.

```bash
kelpmesh debug
```

## KelpMesh pre-commit

Validate SQL files and detect circular dependencies. Designed for CI/pre-commit hooks.

```bash
KelpMesh pre-commit [options]
```

Options:
- `--project-dir` — Project directory (default: current directory)

## KelpMesh orchestrate

Multi-project orchestration across repositories.

```bash
KelpMesh orchestrate [options]
```
