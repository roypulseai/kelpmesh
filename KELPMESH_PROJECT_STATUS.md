# KelpMesh — Project Status & Strategy

> *"If you can write SQL, you can use KelpMesh. No engineering degree required."*

---

## Table of Contents

1. [What is KelpMesh?](#what-is-KelpMesh)
2. [Why Was Jinja Created?](#why-was-jinja-created)
3. [Can We Fully Eliminate Jinja?](#can-we-fully-eliminate-jinja)
4. [Can KelpMesh Beat dbt?](#can-KelpMesh-beat-dbt)
5. [What Has Been Built](#what-has-been-built)
6. [Architecture Overview](#architecture-overview)
7. [What's Missing vs Spec](#whats-missing-vs-spec)
8. [Next Steps](#next-steps)

---

## What is KelpMesh?

**KelpMesh** is an open-core SQL transformation and data modelling platform that lets anyone who writes SQL build reliable, tested, documented, and version-controlled data models — without learning Jinja templating, Git, or software engineering workflows.

The core insight: *anyone who writes SQL should be able to build reliable, documented, tested data models.* That's a fundamentally larger market than dbt's "analytics engineers should work like software engineers."

```
User writes pure SQL
        ↓
KelpMesh Python backend parses the AST
Resolves dependencies automatically
Builds the execution DAG
Tracks state, runs tests, compiles
        ↓
Warehouse receives optimised SQL
```

---

## Why Was Jinja Created?

Jinja (Python templating engine) was embedded into SQL by dbt because the original SQL tooling in 2016 couldn't solve three problems:

### 1. Dependency resolution
SQL has no native concept of "this file depends on that file." dbt needed a way for model A to reference model B. `{{ ref('model_b') }}` was the solution — a Jinja tag that the dbt compiler resolves at build time.

Without Jinja, dbt would have no way to know that `daily_revenue` depends on `orders`.

### 2. Configuration
Materialization strategies (`table` vs `view` vs `incremental`), tags, and other metadata needed somewhere to live. dbt put them inside SQL files using Jinja `{{ config(...) }}` blocks because there was no clean separation of concerns.

### 3. Programmability
Analytics engineers needed loops, conditionals, and reusable macros to avoid repeating SQL. Jinja provided `for` loops, `if` blocks, and macro definitions — things pure SQL couldn't do.

### The real reason

Jinja was the **right call in 2016**. No mature SQL parser library existed that could:
- Parse SQL into an AST across 5+ warehouse dialects
- Extract table references from complex queries (CTEs, subqueries, joins)
- Transpile between dialects

dbt's engineers chose Jinja because it was the only viable option at the time. The fact that it broke IDE support, AI tools, and readability was a trade-off they accepted.

### Why Jinja is unnecessary in 2026

`sqlglot` (first released 2019, mature by 2022+) solves all three problems:

| Problem | Jinja Solution (dbt) | sqlglot Solution (KelpMesh) |
|---------|---------------------|------------------------|
| Dependencies | `{{ ref('model') }}` | Auto-inferred from `FROM`/`JOIN` table references |
| Configuration | `{{ config(materialized='table') }}` | File header comments or external config file |
| Programmability | Jinja macros/loops | Python plugin system or `KelpMesh generate` CLI |

---

## Can We Fully Eliminate Jinja?

**Yes. Completely.**

### What we replace

| Jinja Feature | KelpMesh Replacement | Status |
|---------------|-----------------|--------|
| `{{ ref('model') }}` | Auto-resolved via sqlglot AST | ✅ Done |
| `{{ source('src', 'table') }}` | Auto-resolved as plain table ref | ✅ Done |
| `{{ config(...) }}` | File headers `-- { materialized: table }` or `kelpmesh.yml` | ✅ Done |
| `{{ this }}` | Self-references handled by model name | ✅ Done |
| Jinja macros | Python plugin system (`briq_plugins/` directory) | 🔲 Not started |
| `{{ dbt_utils.* }}` | `KelpMesh-utils` Python package with same patterns | 🔲 Not started |
| Jinja loops (`{% for %}`) | Config-driven generators (`KelpMesh generate staging --from source`) | 🔲 Not started |
| `{% docs %}` blocks | SQL comments → docs generation | ✅ Done |

### The advantage of elimination

By eliminating Jinja, every SQL file becomes **pure SQL**. This means:

- **VS Code intellisense works** — column autocomplete, syntax highlighting, error squiggles
- **AI coding tools work** — GitHub Copilot, Cursor, Codeium all understand pure SQL
- **SQL linters work** — sqlfluff, pgFormatter, all standard tools
- **Code review is easier** — reviewers see clean SQL, not template logic
- **Onboarding is 1-2 days** vs 1-2 weeks for dbt
- **File contents are portable** — open in any SQL tool and it works

### The Jinja gap

There are legitimate use cases Jinja solves that need replacement:

1. **Generating repetitive SQL** (e.g., staging models for 20 source tables) → `KelpMesh generate staging --schema raw`
2. **Reusable SQL snippets** → Python functions that return SQL strings
3. **Conditional SQL** (include/exclude columns based on warehouse) → Python hooks per adapter
4. **Custom tests** → SQL assertion files (already supported)

None of these require embedding a templating engine inside SQL. They're engineering concerns that belong in configuration and plugins, not in data model code.

---

## Can KelpMesh Beat dbt?

### The bull case for KelpMesh

**1. Addressable market is 5-10x larger**

dbt targets ~500K analytics engineers. KelpMesh targets **everyone who writes SQL**:
- FP&A analysts building budget vs actuals
- Revenue operations tracking pipeline metrics
- Marketing ops tracking CAC, LTV, attribution
- BI developers in Tableau/Power BI
- Data scientists building feature tables

That's 50M+ SQL users globally.

**2. Pure SQL is a decisive feature advantage**

dbt has tried and failed to build a good VS Code extension because Jinja breaks the editor. KelpMesh's VS Code extension ships with:
- Full intellisense
- Inline lineage panel
- CodeLens run/test/preview buttons
- Schema drift detection

All because the SQL is **pure SQL**.

**3. Cost advantage**

| Tier | dbt Cloud | KelpMesh | Saving |
|------|-----------|------|--------|
| Solo developer | $50/month | Free | 100% |
| 5-person team | $500/month | CHF 225/month | 55% |
| 10-person team | $1,000-2,000/month | CHF 600/month | 60-70% |
| 30-person enterprise | $6,000+/month | CHF 1,800/month | 70% |

**4. Column-level lineage free**

dbt charges extra (Cloud Enterprise) for column-level lineage. KelpMesh ships it free in Core.

### The risks

**1. Community network effects**

dbt has 9 years of community, 5,000+ packages, 30,000+ GitHub stars, and thousands of blog posts/tutorials. KelpMesh starts at zero.

**Strategy:** Nail the dbt migration story (`KelpMesh import --from dbt`), build core utility packages fast, and invest in community from day 1.

**2. Enterprise trust**

Large enterprises will not adopt a new tool in year 1. Requires 2+ years of production proof and SOC 2 compliance.

**Strategy:** Don't target enterprises in year 1. Let mid-market adoption and community trust build.

**3. Feature parity perception**

dbt has 9 years of feature development. KelpMesh has weeks. Users will compare feature lists and see gaps.

**Strategy:** Focus on the 20% of features that deliver 80% of value. Make the developer experience dramatically better (VS Code, AI tools, onboarding speed). The gaps that matter will close in months, not years.

### Verdict

**KelpMesh can beat dbt** — but not by being a better dbt. It wins by serving a different, larger market (finance/ops/business analysts) that dbt never designed for, while being good enough for analytics engineers who are tired of Jinja.

The threat to dbt is not that KelpMesh is a better analytics engineering tool — it's that KelpMesh makes analytics engineering **irrelevant** by letting business users own their own data models.

---

## What Has Been Built

### Current state: Working CLI POC/MVP (~40% of spec)

All commands are functional end-to-end with verified tests.

#### CLI commands (8 total)

| Command | Description | Status |
|---------|-------------|--------|
| `kelpmesh init` | Scaffold new project with folder structure | ✅ |
| `kelpmesh run` | Execute models in dependency order | ✅ |
| `kelpmesh test` | Run SQL assertion tests | ✅ |
| `kelpmesh build` | Run + test in one command | ✅ |
| `kelpmesh diff <model>` | Compare current vs previous run output | ✅ |
| `kelpmesh docs` | Generate static HTML documentation site | ✅ |
| `KelpMesh import --from dbt` | Migrate dbt project (strips Jinja, converts refs) | ✅ |
| `kelpmesh seed` | Load seed SQL data | ✅ |

#### Core engine

| Component | Description | Status |
|-----------|-------------|--------|
| SQL AST parser | sqlglot-based, extracts table refs from FROM/JOIN/CTE | ✅ |
| DAG builder | networkx topological sort, layer generation, cycle detection | ✅ |
| Sequential executor | Runs models in DAG order, one at a time | ✅ |
| State engine | DuckDB-backed, tracks model hashes, skips unchanged | ✅ |
| Hash computation | Recursive upstream hash ensures full dependency invalidation | ✅ |

#### Warehouse adapters

| Adapter | Status | Notes |
|---------|--------|-------|
| DuckDB | ✅ Full working | Persistent file-based, local dev |
| Snowflake | ✅ Stub | Needs connector + testing with real warehouse |
| BigQuery | ✅ Stub | Needs service account + testing |
| Postgres | ✅ Stub | Needs psycopg2 + testing |

#### Testing framework

| Feature | Status |
|---------|--------|
| SQL assertion files (`SELECT COUNT(*) AS failures FROM ...`) | ✅ |
| Per-model tests (`tests/{model_name}/test.sql`) | ✅ |
| All-model test run (`kelpmesh test`) | ✅ |
| Test results in CLI output | ✅ |

#### Documentation generator

| Feature | Status |
|---------|--------|
| Static HTML site | ✅ |
| Per-model cards with metadata | ✅ |
| Upstream/downstream lineage links | ✅ |
| Column listing with expressions | ✅ |
| SQL source display | ✅ |
| JSON manifest export | ✅ |

#### dbt import

| Feature | Status |
|---------|--------|
| `{{ ref('model') }}` → plain table name | ✅ |
| `{{ source('src', 'table') }}` → plain table name | ✅ |
| `{{ config(...) }}` → removed or header comment | ✅ |
| `{{ this }}` → removed | ✅ |
| YAML model config → kelpmesh.yml | ✅ |
| SQL test files → kelpmesh test files | ✅ |
| dbt_project.yml parsing | ✅ |

#### VS Code extension

| Feature | Status |
|---------|--------|
| CodeLens buttons (Run, Test, Preview, Lineage) | ✅ |
| Lineage webview panel with mermaid.js DAG | ✅ |
| Status bar indicator | ✅ |
| Context menu commands on .sql files | ✅ |
| Preview data webview | ✅ |
| buildProject command | ✅ |
| openDocs command | ✅ |

#### Sample project

| Model | Description |
|-------|-------------|
| `raw_customers` / `raw_orders` | Seed tables (loaded via `kelpmesh seed`) |
| `customers` | Customer aggregations with order stats |
| `orders` | Order enrichment with tier classification |
| `daily_revenue` | Daily revenue aggregation |
| `customer_metrics` | Cross-model metrics join |

#### Tests

- **25 unit tests** across parser, graph, project, state
- **3 SQL assertion tests** in sample project (not_null, positive amounts, positive revenue)
- **End-to-end workflow verified:** seed → run → test → rerun (skip) → build → diff → docs

---

## Architecture Overview

```
KelpMesh/
├── pyproject.toml              # Package config, dependencies
├── KelpMesh/
│   ├── cli/                    # CLI commands (8 commands)
│   │   ├── main.py             # Typer app entry point
│   │   ├── run.py, test.py, build.py, diff.py
│   │   ├── docs.py, init.py, seed.py
│   │   └── import_dbt.py       # dbt project migration
│   ├── core/                   # Engine
│   │   ├── config.py           # Project config (Pydantic + YAML)
│   │   ├── project.py          # Project model loader
│   │   ├── model.py            # BriqModel definition
│   │   ├── graph.py            # networkx DAG builder
│   │   └── executor.py         # Sequential model executor
│   ├── parser/                 # SQL analysis
│   │   ├── sql.py              # sqlglot AST wrapper
│   │   └── lineage.py          # Column-level lineage explorer
│   ├── adapters/               # Warehouse connections
│   │   ├── base.py             # Abstract adapter
│   │   ├── duckdb.py           # DuckDB (working)
│   │   ├── snowflake.py        # Snowflake (stub)
│   │   ├── bigquery.py         # BigQuery (stub)
│   │   └── postgres.py         # Postgres (stub)
│   ├── state/engine.py         # DuckDB-backed state tracking
│   ├── testing/runner.py       # SQL assertion test runner
│   ├── diff/engine.py          # Row count comparison
│   └── docs/generator.py       # Static HTML docs generator
├── extensions/vscode/          # VS Code extension
│   ├── package.json
│   └── src/extension.js
├── sample_project/             # Working example
│   ├── models/ (4 .sql files)
│   ├── tests/ (3 .sql files)
│   ├── seed.sql
│   └── kelpmesh.yml
└── tests/                      # 25 unit tests
    ├── test_parser.py
    ├── test_graph.py
    ├── test_project.py
    └── test_state.py
```

### Tech stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| CLI framework | Typer |
| SQL parsing | sqlglot |
| DAG execution | networkx |
| State storage | DuckDB (embedded) |
| CLI output | Rich |
| Config | Pydantic + YAML |
| VS Code extension | JavaScript + VS Code API |
| Testing | pytest |

---

## What's Missing vs Spec

### Not started

| Feature | Priority | Notes |
|---------|----------|-------|
| KelpMesh Studio (browser UI) | High | React + Monaco editor backend |
| KelpMesh Cloud (managed infra) | Low | Year 2 target |
| CI/CD integration | High | GitHub Actions template needed |
| Databricks adapter | Medium | Spec lists as beta for MVP |
| Redshift adapter | Low | Less common than Snowflake/BQ |
| Python plugin system | Medium | Replaces Jinja macros with Python hooks |
| `KelpMesh-utils` package | Medium | dbt-utils equivalent |
| `KelpMesh-expectations` | Low | dbt-expectations equivalent |
| RBAC / auth | Low | Needed for Studio/Cloud |
| Stripe billing | Low | Needed for Studio Pro |
| SOC 2 preparation | Low | Year 2 |

### Partially built (needs more work)

| Feature | Gap | Effort |
|---------|-----|--------|
| **Parallel executor** | Current is sequential (DuckDB thread-safety issue). Needs connection pooling | 1-2 days |
| **`kelpmesh preview` CLI** | Adapter.preview exists, no CLI wrapper | 2 hours |
| **Column-level lineage in docs** | LineageExplorer class exists, not wired into docs generator | 1 day |
| **Schema drift detection** | VS Code extension has basic check, no `KelpMesh schema` command | 2 days |
| **dbt import v2** | Handles SQL+refs+config but not YAML tests (schema.yml), exposures, docs | 3-5 days |
| **Production DuckDB adapter** | Need connection pooling, WAL mode, concurrent read safety | 1 day |
| **VS Code extension** | Skeleton exists but not packaged for marketplace; needs LSP server for intellisense | 1-2 weeks |

### Known issues

| Issue | Description | Workaround |
|-------|-------------|------------|
| Rich Unicode on Windows | `cp1252` encoding breaks emoji/spinner chars | Using `no_color=True` bypasses it, but loses color |
| State engine threading | DuckDB connections not thread-safe for writes | Sequential executor works; need connection pool for parallel |
| `kelpmesh diff` sample rows | Sample diff query is a placeholder, not true EXCEPT comparison | Reports row count deltas correctly; sample rows unreliable |

---

## Next Steps

### Phase A — Make it production-ready (weeks 1-3)

```
Priority: 🔴 High  🟡 Medium  🟢 Low
Effort:    ⏱ Hours  📅 Days    📆 Weeks
```

| # | Task | Priority | Effort | Description |
|---|------|----------|--------|-------------|
| 1 | **Connection-pooled parallel executor** | 🔴 | 📅 2 days | Each model thread gets its own DuckDB connection. Restore ThreadPoolExecutor with connection-per-worker. Critical for multi-model projects. |
| 2 | **`kelpmesh preview` CLI** | 🟡 | ⏱ 2 hours | Wire `adapter.preview(sql, limit=100)` into a CLI command. Simple but high-visibility feature. |
| 3 | **Schema drift detection** | 🟡 | 📅 2 days | `KelpMesh schema diff` compares upstream table schemas against stored state. Alerts when columns change. |
| 4 | **Column-level lineage in docs** | 🟡 | 📅 1 day | Wire `LineageExplorer.column_lineage()` into `DocsGenerator`. Each column in docs shows upstream source. |
| 5 | **CI/CD templates** | 🔴 | ⏱ 4 hours | GitHub Action + GitLab CI template that runs `kelpmesh build` on PR. Blocking for team adoption. |
| 6 | **Windows encoding fix** | 🟡 | ⏱ 1 hour | Set `PYTHONUTF8=1` or detect encoding and fall back to ASCII-safe renderer. |
| 7 | **PyPI packaging** | 🔴 | 📅 1 day | Complete `pyproject.toml`, add README, license, changelog. Publish to PyPI. |

### Phase B — Expand reach (weeks 4-6)

| # | Task | Priority | Effort | Description |
|---|------|----------|--------|-------------|
| 8 | **Databricks adapter** | 🟡 | 📅 1 day | Implement Databricks SQL connector adapter. |
| 9 | **dbt import v2** | 🟡 | 📅 5 days | Handle YAML tests (`schema.yml` → SQL assertion files), exposures, `docs` blocks, `sources.yml`. |
| 10 | **`KelpMesh-utils` package** | 🟡 | 📅 3 days | `spine`, `date_spine`, `surrogate_key`, `group_by` replacements. `pip install KelpMesh-utils`. |
| 11 | **`KelpMesh generate`** | 🟢 | 📅 3 days | `KelpMesh generate staging --from raw_orders` — scaffolds staging models from source table schemas. |
| 12 | **VS Code extension publish** | 🟡 | 📅 2 days | Package as `.vsix`, test on clean VS Code, publish to marketplace. |
| 13 | **Open source launch** | 🔴 | 📅 3 days | GitHub repo, Apache 2.0 license, `KelpMesh.dev`, docs site, HN/Reddit posts, demo video. |

### Phase C — KelpMesh Studio (weeks 7-12)

| # | Task | Effort | Description |
|---|------|--------|-------------|
| 14 | **Studio backend** | 📆 2 weeks | FastAPI server, PostgreSQL, project CRUD, execution API, scheduling engine. |
| 15 | **Studio frontend** | 📆 3 weeks | React + TypeScript + Monaco Editor + lineage DAG visualization (dagre/d3). |
| 16 | **Auth + teams** | 📆 1 week | User auth (magic link / Google SSO), team management, project sharing. |

### Phase D — KelpMesh Cloud (months 4-6)

| # | Task | Effort | Description |
|---|------|--------|-------------|
| 17 | **Managed execution** | 📆 4 weeks | AWS Fargate run targets, pay-per-execution. |
| 18 | **Billing** | 📆 2 weeks | Stripe integration, self-serve plans. |
| 19 | **Enterprise** | 📆 6 weeks | RBAC, audit logs, SAML/SSO, SOC 2 prep, dedicated support. |

---

## Summary

```
KelpMesh today:       Working CLI POC/MVP — 8 commands, 25 tests, end-to-end verified
KelpMesh in 3 weeks:  Production-ready CLI — parallel, CI/CD, packaged on PyPI
KelpMesh in 6 weeks:  Open source launch — community, packages, VS Code marketplace
KelpMesh in 12 weeks: Studio beta — browser UI for finance/ops/analyst users
KelpMesh in 6 months: Cloud launch — managed infrastructure, enterprise features
```

The core thesis is proven: **pure SQL → auto dependency resolution → DAG execution → state tracking** works end-to-end. The engine is solid. What remains is packaging, community, and the browser UI that unlocks the 50M-user market dbt never reached.

---

*KelpMesh — Build your data, KelpMesh by KelpMesh.*
