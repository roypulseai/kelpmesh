# KelpMesh

**Code-native data transformation platform — SQL and Python models, open-source alternative to dbt.**

KelpMesh lets anyone who writes SQL build reliable, documented, tested data models — without learning Jinja templating, Git, or software engineering workflows.

```bash
pip install KelpMesh
kelpmesh init my_project
cd my_project
kelpmesh run
```

## Why KelpMesh?

dbt forced analysts to learn Jinja templating — a Python-style macro language embedded inside SQL. This breaks IDE intellisense, AI coding assistants, SQL linters, and code readability.

KelpMesh's thesis: *anyone who writes SQL should be able to build reliable, documented, tested data models.*

## Key Features

- **Pure SQL** — no Jinja, no macros, just clean SQL
- **Column-level lineage** — free, not enterprise-locked
- **27 CLI commands** — full data workflow from init to deploy
- **Cross-warehouse** — DuckDB, Snowflake, BigQuery, Postgres, Databricks, Microsoft Fabric
- **Security suite** — audit logging, RLS, column masking, data classification, PII erasure, secrets scanning, encryption
- **dbt migration** — automatic conversion of models, tests, sources, seeds
- **No telemetry** — zero phone-home, enforced at code level
- **nFADP / GDPR ready** — Swiss law-compliant access controls

## Quick Links

- [Installation](guide/installation.md)
- [Quickstart](guide/quickstart.md)
- [CLI Reference](cli/index.md)
- [Security Overview](security/index.md)
- [Migration from dbt](migration/from-dbt.md)

## Community

- [Discord](https://discord.gg/dPAPDn4BF)
- [GitHub](https://github.com/RoyPulseAI/kelpmesh)
- [X / Twitter](https://x.com/kelpmesh_dev)
