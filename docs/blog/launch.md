# Announcing briq — Pure SQL Data Transformation

*June 27, 2026*

Today we're releasing **briq 0.2**, a pure SQL transformation and data modelling platform — a modern alternative to dbt.

**No Jinja. No macros. Just clean, portable SQL.**

## The problem with dbt

dbt was revolutionary when it launched. It brought software engineering practices — testing, documentation, version control — to data transformation.

But there's a problem: **dbt forces analysts to learn Jinja templating**.

Every dbt model looks like this:

```sql
{{ config(materialized='table') }}

SELECT
    {{ ref('orders') }}.customer_id,
    SUM({{ ref('orders') }}.amount) AS total
FROM {{ ref('orders') }}
JOIN {{ ref('customers') }} ON ...
```

That's not SQL. It's SQL contaminated with a templating language. This breaks:

- **IDE intellisense and autocomplete**
- **AI coding assistants** — Copilot, Cursor, and Codeium can't parse Jinja-templated SQL
- **SQL linters and formatters**
- **Code review** — reviewers must mentally parse Jinja to understand the query
- **Onboarding** — new team members must learn both SQL and Jinja

## briq's approach

briq's thesis is simple: **anyone who writes SQL should be able to build reliable, documented, tested data models.**

Here's the same model in briq:

```sql
SELECT
    orders.customer_id,
    SUM(orders.amount) AS total
FROM orders
JOIN customers ON ...
```

Just SQL. Dependencies are resolved automatically by parsing the SQL AST. No refs, no config blocks, no macros.

## What briq ships with

### Column-level lineage — free
Trace every column back to its source. **Not locked behind an enterprise license.** Every user gets full column-level lineage.

### Cross-warehouse support
DuckDB, Snowflake, BigQuery, Postgres, Databricks, and **Microsoft Fabric**.

### Built-in security suite
- **Audit logging** — append-only JSONL trail of every action
- **Row-level security** — policy-based row filters per role
- **Column masking** — inject SQL-level masks based on sensitivity and role
- **Data classification** — 25 built-in rules + custom YAML overrides
- **PII erasure** — right to be forgotten with dry-run support
- **Secrets scanning** — 13 pattern types for hardcoded credentials
- **Transparent encryption** — AES-256-GCM for project state

Designed for nFADP (Swiss law), GDPR, and SOC 2 compliance.

### 27 CLI commands
`init`, `run`, `test`, `build`, `diff`, `preview`, `docs`, `ls`, `clean`, `debug`, `seed`, `schema diff`, `import`, `pre-commit`, `compare`, `orchestrate`, `scan secrets`, `security audit/classify/mask/rls/clean-pii/status/roles` — the full data workflow from setup to deploy.

### dbt migration
```bash
briq import ./dbt-project --output ./briq-project
```

Converts models, tests, sources, seeds, snapshots, and analyses. Compare outputs during migration:

```bash
briq compare --model orders --dbt ../dbt-project
```

### No telemetry
**Zero phone-home.** Enforced at code level — briq refuses to start if posthog, sentry_sdk, datadog, or any analytics package is loaded.

## Getting started

```bash
pip install briq
briq init my_project
cd my_project
briq run
```

## What's next

This is briq 0.2 — beta but production-ready. We're working on:

- **briq Studio** — web UI for visual lineage and project management (freemium)
- **briq Cloud** — hosted execution, team management, SSO (paid)

## Try it today

- **Docs**: [briq.dev](https://briq.dev)
- **Code**: [github.com/briq-dev/briq](https://github.com/briq-dev/briq)
- **Community**: [Discord](https://discord.gg/briq)

*Build your data, briq by briq.*
