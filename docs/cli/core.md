# Core Commands

## briq init

Scaffold a new briq project.

```bash
briq init [project_name] [options]
```

Options:
- `--encrypt` — Initialize with state encryption support

## briq run

Execute models in dependency order.

```bash
briq run [options]
```

Options:
- `--select` — Model selection expression (`+model`, `model+`, `@model`)
- `--full-refresh` — Re-run all models regardless of state
- `--threads` — Number of parallel threads (default: 4)

## briq test

Run SQL assertion tests.

```bash
briq test [options]
```

Options:
- `--warn` — Treat test failures as warnings (non-blocking)
- `--select` — Test selection expression

## briq build

Run models then tests in a single command.

```bash
briq build [options]
```

## briq diff

Compare current model output against the previous run.

```bash
briq diff <model_name>
```

## briq preview

Preview model data from the warehouse.

```bash
briq preview <model_name> [options]
```

Options:
- `--limit` — Number of rows to show (default: 100)

## briq docs

Generate static HTML documentation for your project.

```bash
briq docs [options]
```

Options:
- `--serve` — Serve docs with a local HTTP server
- `--port` — Port for HTTP server (default: 8000)

## briq ls

List models with their status and materialization type.

```bash
briq ls [options]
```

## briq clean

Remove target/ directory and reset project state.

```bash
briq clean
```

## briq seed

Load seed SQL data into the warehouse.

```bash
briq seed <seed_file.sql>
```

## briq schema diff

Detect schema drift by comparing current warehouse schema against stored schema.

```bash
briq schema diff
```

## briq debug

Show project health summary including encryption status, warehouse connection, and security posture.

```bash
briq debug
```

## briq pre-commit

Validate SQL files and detect circular dependencies. Designed for CI/pre-commit hooks.

```bash
briq pre-commit [options]
```

Options:
- `--project-dir` — Project directory (default: current directory)

## briq orchestrate

Multi-project orchestration across repositories.

```bash
briq orchestrate [options]
```
