# briq

Pure SQL transformation and data modelling platform — a modern alternative to dbt.

No Jinja. No macros. Just clean, portable SQL that works with VS Code, AI assistants, and every major warehouse.

```bash
pip install briq
briq init my_project
cd my_project
briq run
briq test
briq docs
```

## Why briq?

**dbt's thesis:** *analytics engineers should work like software engineers.*

**briq's thesis:** *anyone who writes SQL should be able to build reliable, documented, tested data models.*

| | dbt | briq |
|---|---|---|
| Model syntax | Jinja-templated SQL | Pure SQL |
| Learning curve | Weeks | Minutes |
| AI assistant support | Broken (templating confuses Copilot/Cursor) | Full |
| IDE intellisense | Jinja breaks it | Works natively |
| Column lineage | Enterprise only | Free |
| Schema drift detection | Manual | Built-in |
| Audit logging | Not included | Built-in, append-only JSONL |
| Row-level security | Not included | Built-in, policy-based |
| Column masking | Not included | Built-in, role-based |
| Data classification | Not included | Built-in, YAML + heuristics |
| PII erasure | Not included | Built-in (right to be forgotten) |
| Secrets scanning | Not included | Built-in, 13 pattern types |
| Encryption at rest | Not included | Transparent AES-256-GCM |

## Features

- **Pure SQL** — no Jinja macros, no YAML config overhead, just SQL
- **Column-level lineage** — trace every column back to its source (free, not enterprise-locked)
- **27 CLI commands** — run, test, build, diff, preview, schema drift, docs, ls, debug, clean, seed, compare, import, pre-commit, scan secrets, security audit/classify/mask/rls/clean-pii/status/roles
- **Cross-warehouse** — DuckDB, Snowflake, BigQuery, Postgres, Databricks, Microsoft Fabric
- **dbt migration** — `briq import` converts models, YAML tests, sources, seeds, snapshots, analyses
- **Materializations** — view, table, incremental (merge/append), ephemeral (CTE)
- **Model selection** — `+model`, `model+`, `@model` for subset DAG runs
- **Schema drift detection** — `briq schema diff`
- **Test severity** — `briq test --warn` for non-blocking quality checks
- **Security suite** — audit logging, role-based access, column masking, RLS, data classification, PII erasure, secrets scanning, transparent encryption
- **nFADP / GDPR ready** — Swiss law-compliant access controls, data classification, audit trail
- **Integrations** — Airflow (`briq-airflow`), GitHub Actions, GitLab CI, pre-commit, VS Code
- **Cross-platform** — Windows, macOS, Linux
- **No telemetry** — zero phone-home, enforced at code level

## Quickstart

```bash
pip install briq
briq init my_project
cd my_project
briq run
briq test
briq build
briq docs
briq ls
```

## Security

```bash
# Scan for hardcoded credentials
briq scan secrets --fail

# View audit trail
briq security audit

# Classify data columns
briq security classify --init
briq security classify --table orders

# Preview column masking
briq security mask --table users --columns email,phone --role viewer

# List RLS policies
briq security rls

# Erase PII (right to be forgotten)
briq security clean-pii --id-col email --id-value user@example.com --dry-run

# Encrypt project state
briq init --encrypt

# Check security status
briq security status
```

## Documentation

Full documentation at [briq.dev](https://briq.dev) or run `briq docs` in any project.

## Integrations

| Tool | Package / Link |
|------|---------------|
| Airflow | `pip install briq-airflow` — `BriqOperator`, `BriqDag` |
| GitHub Actions | `.github/actions/briq-build` |
| GitLab CI | `ci/gitlab.yml` template |
| Pre-commit | `.pre-commit-hooks.yaml` — `briq-validate` |
| VS Code | [briq extension](https://marketplace.visualstudio.com/items?briq) |

## Migration from dbt

```bash
briq import ./dbt-project --output ./briq-project
```

Converts models, SQL tests, schema.yml tests (not_null, unique, accepted_values, relationships), sources, seeds, snapshots, and analyses.

Compare outputs during migration:

```bash
briq compare --dbt ../dbt-project
```

## Community

- [Discord](https://discord.gg/briq) — chat, support, and community
- [GitHub Issues](https://github.com/briq-dev/briq/issues) — bug reports and feature requests
- [Twitter / X](https://x.com/briq_dev) — product updates

## Development

```bash
git clone https://github.com/briq-dev/briq
cd briq
pip install -e ".[dev]"
python -m pytest tests/
```

## Author

briq is designed and built by **Saikat Roy** ([@saikatxtreme](https://github.com/saikatxtreme)).

## License

Apache 2.0 — see [LICENSE](LICENSE).
