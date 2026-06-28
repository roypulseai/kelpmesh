# CLI Reference

All 27 CLI commands for the KelpMesh data platform.

## Core Commands

| Command | Description |
|---------|-------------|
| `kelpmesh init` | Scaffold a new KelpMesh project |
| `kelpmesh run` | Execute models in dependency order |
| `kelpmesh test` | Run SQL assertion tests |
| `kelpmesh build` | Run models + tests |
| `kelpmesh diff <model>` | Compare current vs previous run |
| `kelpmesh preview <model>` | Preview model data (100 rows) |
| `kelpmesh docs` | Generate static HTML documentation |
| `kelpmesh ls` | List models with status |
| `kelpmesh clean` | Remove target/ and reset state |
| `kelpmesh debug` | Show project health summary |
| `kelpmesh seed <file>` | Load seed SQL data |
| `KelpMesh schema diff` | Detect schema drift |
| `KelpMesh import --from dbt` | Migrate from dbt project |
| `KelpMesh pre-commit` | Validate SQL + check for cycles |
| `KelpMesh compare` | Compare KelpMesh output with dbt output |
| `kelpmesh docs-manifest` | Output project manifest as JSON |
| `KelpMesh orchestrate` | Multi-project orchestration |
| `KelpMesh deps` | Install KelpMesh package dependencies |

## Security Commands

| Command | Description |
|---------|-------------|
| `kelpmesh scan secrets` | Scan for hardcoded credentials |
| `kelpmesh scan generate-key` | Generate encryption key |
| `KelpMesh security audit` | View audit trail |
| `KelpMesh security classify` | Classify data columns |
| `KelpMesh security mask` | Preview column masking |
| `KelpMesh security rls` | List RLS policies |
| `KelpMesh security clean-pii` | Erase PII data |
| `KelpMesh security status` | Security subsystem status |
| `KelpMesh security roles` | List available roles |

## Model Selection

```bash
# Run model + all upstream dependencies
kelpmesh run --select +model

# Run model + all downstream dependencies
kelpmesh run --select model+

# Run full DAG subset around model
kelpmesh run --select @model
```
