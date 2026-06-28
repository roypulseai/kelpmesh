# KelpMesh — Roadmap

> **Vision:** The best way to build, test, and share data models — for everyone who writes SQL.
> **Compete with:** dbt Core + dbt Cloud + dbt Explorer + MetricFlow.

---

## Module Architecture

KelpMesh ships as three independent products that share a common core engine:

| Module | OSS? | Competes with |
|--------|------|---------------|
| **KelpMesh-core** | Apache 2.0 | dbt Core |
| **KelpMesh-studio** | Open-core (Studio free, Pro paid) | dbt Cloud IDE + dbt Explorer |
| **KelpMesh-cloud** | Commercial | dbt Cloud managed infra |

---

## dbt Platform Pillars — Coverage Status

dbt organises their platform around 6 pillars. This is KelpMesh's coverage and roadmap per pillar.

| Pillar | KelpMesh-core | KelpMesh-studio | Phase |
|--------|-----------|-------------|-------|
| **Transformation** | 75% ✅ | — | Phase B closes to 100% |
| **Orchestration** | 40% 🟡 | Studio scheduler | Phase C |
| **Observability** | 55% 🟡 | Run history UI | Phase C + Studio |
| **Catalog** | 50% 🟡 | Explorer UI | Phase B + Studio |
| **Semantic Layer** | 5% 🔴 | Metric explorer | Phase E |
| **Mesh** | 0% 🔴 | Governance UI | Phase F |

---

## Phase A — Production-ready CLI ✅ Done

_Goal: Make the CLI shippable and trustworthy._

| Item | Status |
|------|--------|
| Parallel executor + DuckDB connection pool | ✅ |
| Live progress output (`kelpmesh run`, `kelpmesh build`) with per-model timing | ✅ |
| `kelpmesh preview` CLI | ✅ Fixed (null display, column style bug) |
| Schema drift detection (`KelpMesh schema diff`) | ✅ |
| Column-level lineage in docs (free) | ✅ |
| Windows UTF-8 encoding | ✅ |
| Package CI workflow (pytest on 3.11/3.12/3.13, 3 OS) | ✅ |
| PyPI-ready packaging (hatchling + `python -m build`) | ✅ |
| CHANGELOG.md | ✅ |
| Fix DuckDB encryption kwarg bug | ✅ |
| 92 tests passing | ✅ |

---

## Phase B — dbt Transformation Parity 🔵 Current

_Goal: Any dbt user can switch to KelpMesh and find everything they rely on._

### B1 — Generic tests (schema.yml)
The #1 visible gap for dbt migrants. dbt users declare `tests: not_null` in YAML; KelpMesh must support this.

- Parse `schema.yml` / `models.yml` in `models/` directory
- Auto-generate SQL assertions for: `not_null`, `unique`, `accepted_values`, `relationships`
- Support test `severity: warn|error` in YAML
- Wire into `kelpmesh test` — runs YAML-defined tests alongside SQL assertion files
- **Files:** `KelpMesh/testing/schema_tests.py` (new), `KelpMesh/testing/runner.py`, `KelpMesh/cli/test.py`

### B2 — Snapshots (SCD Type 2)
Track slowly-changing dimensions. First-class `materialized: snapshot` support.

- `unique_key`, `updated_at`, `strategy: timestamp|check` config in SQL header comment
- Creates/updates history table with `_scd_id`, `_valid_from`, `_valid_to`, `_is_current`
- DuckDB implementation first; other adapters follow
- `KelpMesh snapshot` CLI command
- **Files:** `KelpMesh/cli/snapshot.py` (new), `KelpMesh/adapters/base.py`, `KelpMesh/adapters/duckdb.py`, `KelpMesh/core/model.py`

### B3 — Interactive DAG in docs
Replace text-only lineage links with a rendered graph.

- Add Mermaid.js flowchart to `kelpmesh docs` HTML output
- Left-to-right layered layout from DAG topological generations
- Clickable nodes scroll to model card
- **Files:** `KelpMesh/docs/generator.py`

### B4 — YAML descriptions in docs
Pull column and model descriptions from `schema.yml` into the docs site.

- Parse `schema.yml` for model/column `description:` fields
- Merge into `DocsGenerator` — show in model cards alongside SQL-inferred columns
- **Files:** `KelpMesh/core/schema_yaml.py` (new), `KelpMesh/docs/generator.py`, `KelpMesh/core/project.py`

### B5 — Model contracts
Enforce column names + data types as a breaking-change guard.

- Declare `contract: enforced: true` + columns with `data_type:` in `schema.yml`
- At `kelpmesh run`, validate actual table schema matches declared contract
- Fail loudly with diff if contract is violated
- **Files:** `KelpMesh/core/contract.py` (new), `KelpMesh/core/executor.py`

### B6 — Model versioning (v1/v2)
Safe migrations when a model's interface changes.

- Models can declare `version: 2` and `defined_in: orders_v2`
- `ref('orders')` resolves to latest; `ref('orders', version=1)` pins to old
- Deprecation warnings when consumers reference old versions
- **Files:** `KelpMesh/core/model.py`, `KelpMesh/core/graph.py`, `KelpMesh/parser/sql.py`

### B7 — `KelpMesh generate` scaffolding
Eliminate the tedious "create 20 staging models by hand" problem.

- `KelpMesh generate staging --schema raw` — introspects source tables and generates staging SQL
- `KelpMesh generate model --from orders` — scaffolds a new model referencing an existing one
- **Files:** `KelpMesh/cli/generate.py` (new)

### B8 — Verified adapter tests (Snowflake, BigQuery, Postgres)
The stubs need real warehouse validation.

- Integration test harness that runs against live warehouses in CI (via secrets)
- Verify: CREATE TABLE, CREATE VIEW, incremental merge, schema introspection
- **Files:** `tests/adapters/test_snowflake.py`, `tests/adapters/test_bigquery.py`, `tests/adapters/test_postgres.py`

---

## Phase C — Orchestration + Observability 🔵 Next

_Goal: Manage pipelines with confidence. Know when things break before users do._

### Orchestration
| Item | Description |
|------|-------------|
| `kelpmesh plan` / `KelpMesh apply` | Terraform-style preview: show what will run and why before running |
| Environment isolation | `--env dev/staging/prod` namespaces schemas (e.g. `dev_orders` vs `orders`) |
| Built-in cron scheduler | `KelpMesh schedule add "0 8 * * *" kelpmesh build` — no Airflow needed for simple cases |
| Backfill tracking | Track which incremental date windows have been processed; detect gaps |
| Webhook triggers | POST to `/run` to trigger a build from external systems |

### Observability
| Item | Description |
|------|-------------|
| Anomaly detection | Row count / null rate spikes vs rolling baseline — alert on deviation |
| Alert integrations | Slack, PagerDuty, webhook on test failure, schema drift, or freshness violation |
| Run history store | Persist run outcomes across sessions; queryable via `KelpMesh history` |
| Data health score | Per-model composite score (freshness + test pass rate + drift status) |

---

## Phase D — KelpMesh Studio 🟣

_Goal: The browser UI that unlocks the 50M analyst/ops/FP&A market dbt never designed for._

### Core Studio (self-hostable, free)
- Monaco SQL editor with KelpMesh-aware intellisense (column autocomplete, ref() resolution)
- Live lineage DAG (dagre + d3) — click any node to open the model
- Run / test / preview controls inline in the editor
- Project file tree with status indicators

### Studio Pro (paid)
- Team management — invite members, model ownership, comments
- Scheduling UI — cron schedules with calendar view + failure alerts
- Run history dashboard — pass/fail trends, timing charts per model
- dbt Explorer equivalent — searchable catalog, data health tiles, column lineage explorer

### Tech stack
- Backend: FastAPI + PostgreSQL + SQLAlchemy (scaffold in `extensions/studio/backend/`)
- Frontend: React + TypeScript + Monaco Editor (scaffold in `extensions/studio/frontend/`)
- Auth: magic link + Google SSO
- Pricing: Free (1 user, 20 models) → Pro (CHF 20/user/month) → Team (CHF 45/user/month)

---

## Phase E — Semantic Layer 🟡

_Goal: Define metrics once. Deliver them to any dashboard, BI tool, or LLM._

Competes with: dbt MetricFlow + dbt Semantic Layer.

| Item | Description |
|------|-------------|
| Metric YAML definitions | `name`, `label`, `type` (simple/ratio/cumulative), `measure`, `dimensions`, `filters` |
| MetricFlow-equivalent engine | SQL generation from metric + dimension + filter combo at query time |
| `KelpMesh metric query` CLI | `KelpMesh metric query --metric revenue --group-by date,region --where "date > '2025-01-01'"` |
| Saved queries | Pre-materialised metric + dimension combos as views |
| BI tool exports | Tableau / Looker / Power BI / Metabase connector |
| LLM-ready API | REST endpoint — AI assistants can query metrics by name without writing SQL |
| Metric validation | Catch undefined dimensions, circular metric references at `kelpmesh build` time |

---

## Phase F — Mesh 🔴

_Goal: Manage complexity across teams and warehouses at enterprise scale._

Competes with: dbt Mesh.

| Item | Description |
|------|-------------|
| Cross-project references | `ref('project_b', 'model')` across repo boundaries |
| Producer/consumer contracts | Upstream team publishes interface; downstream team pins to a version |
| Groups + access controls | Restrict which models other projects can reference (`access: private/protected/public`) |
| Multi-platform mesh | Project A on Snowflake, Project B on BigQuery — models linked across warehouses |
| Governance dashboard | Who owns what, who depends on what, contract health across all projects |

---

## Phase G — KelpMesh Cloud ☁️

_Goal: Fully managed execution for teams that don't want to self-host._

| Item | Description |
|------|-------------|
| Managed run targets | AWS Fargate containers per run, pay-per-execution, scale-to-zero |
| Credential vault | Warehouse credentials stored encrypted, never leave the run environment |
| SOC 2 Type I | Swiss data residency option. GDPR + nFADP compliant. |
| RBAC + SSO | SAML/Okta SSO, role-based access, per-model permissions |
| Enterprise pricing | CHF 1,800/month (30 users) → Custom enterprise |

---

## VS Code Extension

Parallel track — not gated on any phase but benefits from each:

| Item | Status |
|------|--------|
| CodeLens (Run / Test / Preview / Lineage) | ✅ Skeleton |
| Mermaid lineage panel | ✅ Skeleton |
| LSP server for SQL intellisense | Phase B |
| Schema-aware column autocomplete | Phase B |
| Marketplace publish | Phase B |

---

## Open Source Launch

Target: after Phase B ships.

- GitHub repo public (`KelpMesh-dev/KelpMesh`), Apache 2.0
- `KelpMesh.dev` docs site live (MkDocs Material — `mkdocs.yml` already configured)
- VS Code extension on marketplace
- Hacker News + r/dataengineering launch post
- Discord server

---

## Success Milestones

| Milestone | Condition |
|-----------|-----------|
| **Shippable** | Phase A complete ✅ |
| **dbt Alternative** | Phase B complete — any dbt project imports and runs |
| **Pipeline Platform** | Phase C complete — orchestration + observability production-ready |
| **Product** | Phase D complete — Studio live, paying users |
| **Enterprise** | Phases E + F + G complete — Mesh, Semantic Layer, Cloud |

---

*Last updated: 2026-06-28*
