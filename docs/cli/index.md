# CLI Reference

All 27 CLI commands for the briq data platform.

## Core Commands

| Command | Description |
|---------|-------------|
| `briq init` | Scaffold a new briq project |
| `briq run` | Execute models in dependency order |
| `briq test` | Run SQL assertion tests |
| `briq build` | Run models + tests |
| `briq diff <model>` | Compare current vs previous run |
| `briq preview <model>` | Preview model data (100 rows) |
| `briq docs` | Generate static HTML documentation |
| `briq ls` | List models with status |
| `briq clean` | Remove target/ and reset state |
| `briq debug` | Show project health summary |
| `briq seed <file>` | Load seed SQL data |
| `briq schema diff` | Detect schema drift |
| `briq import --from dbt` | Migrate from dbt project |
| `briq pre-commit` | Validate SQL + check for cycles |
| `briq compare` | Compare briq output with dbt output |
| `briq docs-manifest` | Output project manifest as JSON |
| `briq orchestrate` | Multi-project orchestration |
| `briq deps` | Install briq package dependencies |

## Security Commands

| Command | Description |
|---------|-------------|
| `briq scan secrets` | Scan for hardcoded credentials |
| `briq scan generate-key` | Generate encryption key |
| `briq security audit` | View audit trail |
| `briq security classify` | Classify data columns |
| `briq security mask` | Preview column masking |
| `briq security rls` | List RLS policies |
| `briq security clean-pii` | Erase PII data |
| `briq security status` | Security subsystem status |
| `briq security roles` | List available roles |

## Model Selection

```bash
# Run model + all upstream dependencies
briq run --select +model

# Run model + all downstream dependencies
briq run --select model+

# Run full DAG subset around model
briq run --select @model
```
