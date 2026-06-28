# KelpMesh — Roadmap

> **Vision:** The best way to build, test, and share data models — for everyone who writes SQL.
> **Competes with:** dbt Core · dbt Cloud · dbt Explorer · MetricFlow · SQLMesh

---

## Status summary

| Phase | Description | Status |
|-------|-------------|--------|
| A | Production-ready CLI | ✅ Done |
| B | dbt transformation parity | ✅ Done |
| C | Orchestration + observability | ✅ Done |
| D | KelpMesh Studio | ✅ Done |
| E | Semantic layer | ✅ Done |
| F | Data mesh | ✅ Done |
| G | CI/CD + VCS integration | ✅ Done |
| H | Studio Pro features + freemium | ✅ Done |
| **I** | **Distribution** | 🔴 Next |
| **J** | **Community launch** | 🔴 Next |
| **K** | **First paying customers** | 🟡 Month 2 |
| **L** | **Enterprise** | 🟡 Month 4+ |

---

## Phases A–H — Completed

### What was built

| Area | Delivered |
|------|-----------|
| **CLI engine** | 30+ commands: run, test, build, plan, compile, ci, docs, preview, diff, seed, ls, import, scan, security, schedule, mesh, metric, export, studio, serve, generate, orchestrate, freshness, history, compare, deps, source, exposure, debug, clean, pre-commit |
| **Warehouse adapters** | 9 total: DuckDB · Postgres · Snowflake · BigQuery · Databricks · Redshift · Fabric · MySQL · Trino — all with incremental merge and SCD Type 2 |
| **SQL macros** | 32 built-in macros, SQL-native (no Jinja), recursive-descent parser, zero-dependency |
| **Python models** | `def model(dbt, session)` interface; DbtProxy + SessionProxy; mixed SQL/Python DAGs |
| **Scheduler** | Built-in cron scheduler (zero external deps); cron + interval syntax |
| **Integrations** | Dagster · Prefect · Airflow · GitHub Actions · GitLab CI · Bitbucket Pipelines |
| **CI/CD** | `kelpmesh ci` with slim CI; PR/MR comments on GitHub, GitLab, Bitbucket (stdlib urllib, zero deps) |
| **Security** | PII classification · RLS · column masking · GDPR erasure · audit log · secret scanning |
| **Studio** | FastAPI + React browser layer; DAG viz; run history; team management |
| **Freemium** | Local HMAC license keys; Free personal / Pro $29 / Business $79 / Enterprise |
| **Data mesh** | Cross-project ref(); access contracts; multi-warehouse mesh |
| **Semantic layer** | Metric YAML; query engine; BI export (LookML, Tableau, PowerBI, Qlik) |
| **VS Code extension** | 37 snippets; model tree; CodeLens run/test/preview/plan; plan panel |
| **dbt migration** | `kelpmesh import` converts models, tests, sources, seeds, snapshots from dbt projects |

---

## Phase I — Distribution (Week 1–2)

_The code is ready. Nothing ships until it can be installed._

| Task | Priority | Notes |
|------|----------|-------|
| **Publish `kelpmesh-core` to PyPI** | 🔴 Critical | `pip install kelpmesh-core` must work for any user |
| **Publish `kelpmesh-studio` to PyPI** | 🔴 Critical | Same |
| **Register kelpmesh.io domain** | 🔴 Critical | Documentation links throughout the codebase point here |
| **Deploy documentation site** | 🔴 Critical | MkDocs Material; minimum: quickstart, adapter config, CLI reference |
| **Publish VS Code extension to marketplace** | 🔴 Critical | Search "KelpMesh" in VS Code must find and install it |
| **Set up GitHub Actions for auto-publish** | 🟡 High | Tag `v0.3.0` → PyPI release; tag `v*-ext` → marketplace publish |
| **Write CONTRIBUTING.md** | 🟡 High | Needed before any community contribution is possible |
| **Verify `kelpmesh import` on a real dbt project** | 🟡 High | End-to-end smoke test on a public dbt Jaffle Shop |

---

## Phase J — Community launch (Week 3–4)

_Get the first 500 users._

| Task | Priority | Channel |
|------|----------|---------|
| **Hacker News "Show HN"** | 🔴 | Title: "Show HN: KelpMesh — pure SQL transformation (no Jinja)" |
| **r/dataengineering launch post** | 🔴 | Lead with the AI/IDE advantage |
| **Product Hunt launch** | 🔴 | Schedule for Tuesday 9am PT; prepare assets in advance |
| **dbt Slack community post** | 🟡 | #tools-and-integrations channel |
| **Discord server** | 🟡 | Set up before launch; announce in all posts |
| **"Why we built KelpMesh" blog post** | 🟡 | Technical narrative: Jinja in 2026 is unnecessary debt |
| **"Migrating from dbt in 10 minutes" guide** | 🟡 | Walk through `kelpmesh import` + before/after SQL comparison |
| **Demo video (5 min)** | 🟡 | Install → init → run → ci PR comment → Studio; screen recording |
| **Twitter/X account (@kelpmesh_dev)** | 🟢 | Release notes, tips, community highlights |

---

## Phase K — First paying customers (Month 2)

_Convert free users to paying Studio Pro/Business._

| Task | Priority | Notes |
|------|----------|-------|
| **Stripe integration for Studio** | 🔴 Critical | No way to charge for Pro/Business without this |
| **Self-serve checkout flow** | 🔴 Critical | User clicks "Upgrade to Pro" → Stripe checkout → license key emailed |
| **License key delivery** | 🔴 Critical | Email with activation instructions on payment success |
| **Support channel** | 🟡 High | Discord `#pro-support` or email help@kelpmesh.io |
| **"Migrate your team from dbt Cloud" guide** | 🟡 High | Target teams paying $500-2000/month for dbt Cloud |
| **Case study: first paying customer** | 🟢 | Blog post once first non-free customer is active |

---

## Phase L — Enterprise (Month 4+)

_Target mid-market data teams (10-50 users)._

| Task | Priority | Notes |
|------|----------|-------|
| **SOC 2 Type I preparation** | 🟡 | Required by most enterprise procurement; 3-6 month timeline |
| **Branch environment isolation** | 🟡 | `--env dev/staging/prod` namespaces schemas per environment — SQLMesh's biggest feature advantage over us today |
| **On-premises deployment guide** | 🟡 | Docker Compose + Kubernetes Helm chart |
| **SAML/Okta SSO** | 🟡 | Required for most enterprise IT approval |
| **Integration tests vs live warehouses in CI** | 🟡 | Snowflake + BigQuery + Postgres; builds trust with enterprise buyers |
| **ClickHouse adapter** | 🟢 | Frequently requested; growing adoption |
| **Virtual environments** | 🟢 | Per-branch warehouse schema isolation at the infrastructure level |

---

## What production readiness actually means

The code is mature. The product is not yet shippable.

**Not blocked on code:**

- PyPI packages not published — `pip install kelpmesh-core` returns "no such package"
- Domain not registered — `kelpmesh.io` is a dead link throughout the codebase
- Documentation site doesn't exist — no quickstart, no adapter docs, no CLI reference
- VS Code extension not on marketplace — "KelpMesh" finds nothing in VS Code
- No Discord community — the `discord.gg/kelpmesh` link returns 404
- No Stripe integration — no way to charge for Studio Pro or Business
- Zero tests for newly built features — macros, CI/CD, and freemium licensing are untest-covered

**Honest timeline to first paying customer:** 6–8 weeks of distribution + community work.

**Honest timeline to $10k MRR:** 4–6 months, assuming community launch lands well.

---

## Success milestones

| Milestone | Condition | Status |
|-----------|-----------|--------|
| **Buildable** | CLI runs end-to-end on DuckDB | ✅ Done |
| **Feature-complete v1** | All dbt features covered + CI/CD + Studio | ✅ Done |
| **Installable** | PyPI publish + docs site live | 🔴 Not done |
| **Discoverable** | VS Code marketplace + HN/Reddit launch | 🔴 Not done |
| **Revenue** | First paying Studio Pro customer | 🔴 Not done |
| **Community** | 500 GitHub stars, active Discord | 🔴 Not done |
| **Enterprise-ready** | SOC 2, SSO, integration test suite | 🟡 Month 4+ |

---

*Last updated: 2026-06-28*
