# briq — Full Roadmap to Production

> **Goal:** Make briq fully functional, production-ready, and world-class — capable of replacing dbt for any team.

---

## Overview

briq is currently a working CLI POC/MVP. This roadmap covers everything needed to go from POC to a product that teams rely on in production. The phases are ordered by dependency — each phase builds on the previous.

**Legend:**
- `🔴 Critical` — blocks production use
- `🟡 High` — important for team adoption
- `🟢 Medium` — nice-to-have, quality of life
- `⚪ Low` — future / stretch

---

## Phase 0 — Fix Core Engine (Weeks 1-2)

Make the existing engine production-grade. Nothing else matters until this is solid.

### 0.1 Parallel executor with connection pooling
- **Status:** 🔴 Critical — the executor is currently sequential
- **Work:** Give each worker thread its own DuckDB connection. Restore ThreadPoolExecutor. Add connection pool manager.
- **Files affected:** `briq/core/executor.py`, `briq/adapters/duckdb.py`
- **Testing:** Run 10-model project, verify all run in correct order, no race conditions
- **Exit criteria:** `briq run` with 4+ threads works correctly, no thread-safety crashes

### 0.2 `briq preview` CLI command
- **Status:** 🟡 High — adapter has `preview()` but no CLI
- **Work:** Wire `adapter.preview(sql, limit=100)` into `briq/cli/preview.py`. Output as table.
- **Files affected:** `briq/cli/preview.py` (new), `briq/cli/main.py`
- **Exit criteria:** `briq preview orders` shows 100 rows in terminal

### 0.3 Schema drift detection
- **Status:** 🟡 High — critical for production trust
- **Work:** `briq schema diff` command. Compare upstream table columns vs stored schema. Alert on additions/removals/type changes.
- **Files affected:** `briq/cli/schema.py` (new), `briq/schema/` (new module)
- **Exit criteria:** `briq schema diff` detects when a source table column changes

### 0.4 Column-level lineage in docs generator
- **Status:** 🟡 High — `LineageExplorer` exists but not wired
- **Work:** For each model, trace each SELECT column back to its source columns. Display in docs HTML.
- **Files affected:** `briq/docs/generator.py`, `briq/parser/lineage.py`
- **Exit criteria:** Docs site shows "Column X comes from table Y.column Z" for each column

### 0.5 State engine hardening
- **Status:** 🟡 High — needs WAL mode, crash recovery, concurrent access safety
- **Work:** Enable DuckDB WAL mode. Add transaction wrapping around reads/writes. Handle corrupted state files.
- **Files affected:** `briq/state/engine.py`
- **Exit criteria:** Power loss during `briq run` doesn't corrupt state. Two concurrent processes don't conflict.

### 0.6 Windows encoding fix
- **Status:** 🟡 High — blocks Windows users from colored output
- **Work:** Set `PYTHONUTF8=1` or auto-detect console encoding and fall back to ASCII-safe output.
- **Files affected:** `briq/cli/*.py` (all console initializations)
- **Exit criteria:** `briq run` on Windows cmd/PS shows colored tables without UnicodeEncodeError

---

## Phase 1 — Complete Feature Set (Weeks 3-4)

Fill the remaining feature gaps for parity with dbt Core.

### 1.1 `briq ls` — list models command
- **Status:** 🟡 High
- **Work:** `briq ls` lists all models with status (up-to-date / stale / never run), materialization, upstream count
- **Files affected:** `briq/cli/ls.py` (new), `briq/cli/main.py`
- **Exit criteria:** `briq ls` shows formatted table of all models with status, type, deps

### 1.2 `briq clean` — clear target + state
- **Status:** 🟢 Medium
- **Work:** Remove `target/` directory, reset state engine
- **Files affected:** `briq/cli/clean.py` (new)
- **Exit criteria:** `briq clean && briq run` runs all models fresh (no skips)

### 1.3 `briq debug` — debug/status command
- **Status:** 🟢 Medium
- **Work:** Show project config, warehouse connection status, model count, state health
- **Files affected:** `briq/cli/debug.py` (new)
- **Exit criteria:** `briq debug` prints project health summary

### 1.4 Databricks adapter
- **Status:** 🟡 High — spec lists as beta for MVP
- **Work:** Implement Databricks SQL connector adapter. Use `databricks-sql-connector` Python package.
- **Files affected:** `briq/adapters/databricks.py` (new), `briq/adapters/__init__.py`
- **Exit criteria:** `briq run` works against a Databricks SQL warehouse

### 1.5 `briq test` improvements
- **Status:** 🟡 High
- **Work:** Support generic test files (not model-specific). Support test severity levels. Add `--warn` flag.
- **Files affected:** `briq/testing/runner.py`, `briq/cli/test.py`
- **Exit criteria:** Tests can be tagged with `warn` vs `error` severity

### 1.6 `briq run --select` / model selection
- **Status:** 🟡 High
- **Work:** Support `+model_name` (upstream), `model_name+` (downstream), `@model_name` (full DAG subset)
- **Files affected:** `briq/core/graph.py`, `briq/core/executor.py`, `briq/cli/run.py`
- **Exit criteria:** `briq run +orders` runs orders and all its upstream dependencies

### 1.7 Materialization strategies
- **Status:** 🟢 Medium
- **Work:** Incremental models (merge/append), ephemeral models (CTE-only), snapshots (type-2 SCD)
- **Files affected:** `briq/core/model.py`, `briq/adapters/*.py`
- **Exit criteria:** Incremental model with `--materialized incremental` works with merge strategy

---

## Phase 2 — Testing & Reliability (Weeks 5-6)

Every regression-causing bug found in production costs 10x more than finding it in tests.

### 2.1 Integration test suite
- **Status:** 🔴 Critical
- **Work:** End-to-end tests that: seed → run → verify row counts → diff → rerun → verify skip. Test every CLI command. Test error paths.
- **Files affected:** `tests/test_integration.py` (new)
- **Exit criteria:** Full integration suite passes on clean Windows + Linux

### 2.2 Adapter acceptance tests
- **Status:** 🔴 Critical
- **Work:** Abstract test suite that every adapter must pass. Tests: table creation, view creation, data types, null handling, increments.
- **Files affected:** `tests/adapters/` (new directory), `tests/adapters/test_base_adapter.py`
- **Exit criteria:** DuckDB adapter passes 100% of acceptance tests

### 2.3 Error handling & user messages
- **Status:** 🟡 High
- **Work:** Every error path shows a helpful message + suggested fix. No bare Python tracebacks shown to users (except `--debug`).
- **Files affected:** All CLI files
- **Exit criteria:** Wrong config → "Did you mean X?" | Missing table → "Run upstream models first" | Cycle detected → "Here's the cycle"

### 2.4 Large project performance test
- **Status:** 🟢 Medium
- **Work:** Test with 100+ models. Measure: parse time, DAG build time, state check time, diff time.
- **Files affected:** `tests/test_performance.py` (new)
- **Exit criteria:** 100 models parse + build DAG in <1s. State check for all models in <2s.

---

## Phase 3 — CI/CD & DevOps (Weeks 7-8)

Make briq a first-class citizen in modern data engineering workflows.

### 3.1 GitHub Action — `briq-build`
- **Status:** 🔴 Critical — blocks team PR workflows
- **Work:** GitHub Action that runs `briq build` on PR. Comments test results on PR. Fails if tests fail.
- **Files affected:** `.github/actions/briq-build/action.yml` (new), `.github/workflows/ci.yml` (new)
- **Exit criteria:** Pushing a PR triggers briq build, results posted as PR comment

### 3.2 GitLab CI template
- **Status:** 🟢 Medium
- **Work:** `.gitlab-ci.yml` template for briq
- **Files affected:** `ci/gitlab.yml` (new)
- **Exit criteria:** Documentation shows copy-paste GitLab CI config

### 3.3 Pre-commit hook
- **Status:** 🟢 Medium
- **Work:** `briq pre-commit` — validates SQL files parse correctly, no circular deps
- **Files affected:** `briq/cli/pre_commit.py` (new), `.pre-commit-hooks.yaml` (new)
- **Exit criteria:** `briq pre-commit` exits non-zero on invalid SQL

### 3.4 PyPI publishing pipeline
- **Status:** 🔴 Critical
- **Work:** GitHub Action that publishes to PyPI on tags. Version management (calver or semver).
- **Files affected:** `.github/workflows/publish.yml` (new), `pyproject.toml`
- **Exit criteria:** Pushing tag `v0.2.0` automatically publishes to PyPI

### 3.5 Airflow integration — `briq-airflow` package
- **Status:** 🟡 High — Airflow is the #1 orchestrator in data engineering
- **Work:** Publish `briq-airflow` Python package providing:
  - `BriqOperator` — executes `briq run` / `briq build` / `briq test` within Airflow tasks, streams logs to Airflow, surfaces test failures as task failures
  - `BriqDag` — helper that auto-generates an Airflow DAG from a briq project's model DAG, respecting dependency layers as task groups
  - Deferrable (`TriggerDagRunOperator`-compatible) operator for long-running models
  - `BriqSensor` — polls briq run status for async execution
  - `BriqRunLink` / `BriqDocsLink` — Airflow extras links to briq docs and run history
- **Repo:** `briq-dev/briq-airflow` (separate package, optional dependency)
- **Files affected:** New repo with `briq_airflow/operators.py`, `briq_airflow/dags.py`, `briq_airflow/example_dags/`
- **Testing:** Run example DAG against LocalExecutor and CeleryExecutor. Verify task retry, failure propagation, log streaming.
- **Documentation:** "Orchestrating briq with Airflow" guide — install, configure, example DAGs, production best practices
- **Exit criteria:** `pip install briq-airflow && BriqOperator(briq_cmd="build", project_dir="/path")` runs a full briq build as an Airflow task

### 3.6 Documentation site
- **Status:** 🟡 High
- **Work:** `briq.dev` — Next.js site with: installation guide, tutorial, CLI reference, Airflow integration guide, example gallery, migration guide
- **Files affected:** `site/` (new directory, Next.js project)
- **Exit criteria:** `briq.dev` is live with docs for all CLI commands and integrations

---

## Phase 4 — dbt Compatibility & Migration (Weeks 9-10)

Make switching from dbt feel like upgrading, not migrating.

### 4.1 `briq import` — YAML test conversion
- **Status:** 🟡 High
- **Work:** Convert dbt `schema.yml` tests to SQL assertion files. Support `not_null`, `unique`, `accepted_values`, `relationships`, `custom`.
- **Files affected:** `briq/cli/import_dbt.py`
- **Exit criteria:** dbt project with YAML tests imports to equivalent briq SQL tests

### 4.2 `briq import` — exposures + metrics
- **Status:** 🟢 Medium
- **Work:** Parse `exposures.yml` and `metrics.yml` from dbt projects
- **Files affected:** `briq/cli/import_dbt.py`
- **Exit criteria:** dbt exposures appear in briq docs as downstream consumers

### 4.3 `briq import` — packages + macros
- **Status:** 🟢 Medium
- **Work:** Identify dbt package usage, suggest briq equivalents. Convert common macros.
- **Files affected:** `briq/cli/import_dbt.py`
- **Exit criteria:** Import report shows "3 dbt packages found, 2 have briq equivalents"

### 4.4 Output comparison tool
- **Status:** 🟡 High
- **Work:** `briq compare --dbt` — run same project in dbt and briq, compare output row-by-row. Critical for migration confidence.
- **Files affected:** `briq/cli/compare.py` (new), `briq/diff/comparison.py` (new)
- **Exit criteria:** `briq compare --dbt` shows "All 7 models produce identical output"

---

## Phase 5 — Package Ecosystem (Weeks 11-12)

Borrow the best idea from dbt's success: the package ecosystem.

### 5.1 `briq-utils` package
- **Status:** 🟡 High
- **Work:** Essential utility functions: `spine`, `date_spine`, `surrogate_key`, `group_by`, `pivot`, `unpivot`, `generate_surrogate_key`
- **Repo:** New repo `briq-dev/briq-utils`
- **Exit criteria:** `pip install briq-utils` and `IMPORT briq_utils` in SQL

### 5.2 `briq-expectations` package
- **Status:** 🟢 Medium
- **Work:** Data quality expectations: `expect_column_to_be_unique`, `expect_column_values_to_be_in_set`, etc.
- **Repo:** New repo `briq-dev/briq-expectations`
- **Exit criteria:** 30+ expectation macros available

### 5.3 Package system for briq
- **Status:** 🟡 High
- **Work:** Allow `briq deps add briq-utils` / `briq deps install`. Track packages in `briq.lock`.
- **Files affected:** `briq/cli/deps.py` (new), `briq/core/packages.py` (new)
- **Exit criteria:** `briq deps add briq-utils && briq deps install` makes utils available

### 5.4 Community package registry
- **Status:** ⚪ Low
- **Work:** Web registry at `packages.briq.dev` — discoverable, searchable packages
- **Exit criteria:** Users can publish and discover packages

---

## Phase 6 — Studio MVP (Months 3-4)

The browser UI that unlocks the 50M-user market dbt never reached.

### 6.1 Studio backend
- **Status:** 🔴 Critical for business users
- **Work:** FastAPI server. Project CRUD. Model CRUD. Run API (sync + async). Test API. Diff API. Schema introspection. Auth (magic link + Google OAuth).
- **Stack:** FastAPI, PostgreSQL, SQLAlchemy, Redis (for async runs)
- **Repo:** `briq-dev/briq-studio`
- **Exit criteria:** User can create project, add SQL files, and run models from browser

### 6.2 Studio frontend
- **Status:** 🔴 Critical for business users
- **Work:** Monaco Editor (same as VS Code). File tree. Run button. Run history panel. Test results panel. DAG visualization (dagre + d3).
- **Stack:** React, TypeScript, Monaco Editor, dagre, d3-force
- **Exit criteria:** Full CRUD on models. Visual DAG. Run + test from browser.

### 6.3 Scheduling engine
- **Status:** 🟡 High
- **Work:** Cron-based scheduling. "Run daily at 8am" UI. Email notifications on failure. Run history calendar.
- **Files affected:** Studio backend scheduling module
- **Exit criteria:** Schedule a model to run daily, it runs, and sends email on failure

### 6.4 Version history
- **Status:** 🟡 High
- **Work:** Every model save creates a version. Compare versions. Rollback to previous version. Like Google Docs for SQL.
- **Files affected:** Studio backend + frontend
- **Exit criteria:** Click "history" on a model, see 10 versions, compare any two

### 6.5 Team collaboration
- **Status:** 🟡 High
- **Work:** Teams, invite members, model ownership, comments on models, Slack notifications
- **Files affected:** Studio backend + frontend
- **Exit criteria:** Team of 5 can collaborate on 20 models with comments and notifications

### 6.6 Studio Pro pricing gateway
- **Status:** 🟡 High
- **Work:** Free tier (1 user, 20 models). Pro (CHF 20/user/month). Team (CHF 45/user/month). Stripe integration.
- **Files affected:** Studio billing module
- **Exit criteria:** User can sign up, get free tier, upgrade to Pro with credit card

---

## Phase 7 — Cloud Launch (Months 5-6)

Managed infrastructure for teams that don't want to self-host.

### 7.1 Managed run targets
- **Status:** 🟡 High
- **Work:** AWS Fargate containers for model execution. Pay-per-run. Auto-scaling to 0.
- **Stack:** AWS ECS + Fargate, Terraform, Docker
- **Exit criteria:** User clicks "Run" in Studio, it executes on AWS, results appear in UI

### 7.2 Multi-project orchestration
- **Status:** 🟢 Medium
- **Work:** Cross-project dependencies. DAG across projects. Orchestration layer.
- **Exit criteria:** Project B can depend on Project A's models

### 7.3 RBAC + SSO
- **Status:** 🟡 High — enterprise requirement
- **Work:** Role-based access control. SAML/Okta SSO. Audit log.
- **Exit criteria:** Enterprise admin can configure SSO and set read/write/admin roles

### 7.4 Enterprise pricing & support
- **Status:** 🟢 Medium
- **Work:** Business (CHF 1,800/month, 30 users). Enterprise (custom). SLA. Dedicated support.
- **Exit criteria:** Enterprise plan has self-serve checkout

### 7.5 SOC 2 preparation
- **Status:** ⚪ Low
- **Work:** SOC 2 Type I audit. Data residency (Swiss option). Encryption at rest + in transit.
- **Exit criteria:** SOC 2 Type I certified

---

## Phase 8 — Community & Growth (Ongoing)

The engine that makes briq self-sustaining.

### 8.1 Open source launch
- **Status:** 🔴 Critical — the foundation of everything
- **Work:** GitHub repo (`briq-dev/briq`), Apache 2.0 license, CONTRIBUTING.md, CODE_OF_CONDUCT.md, good-first-issues
- **Exit criteria:** 100+ GitHub stars in first week

### 8.2 Launch blog post + HN
- **Status:** 🔴 Critical
- **Work:** "We built a dbt alternative. Here's why." Blog post with demo GIF. Hacker News post. r/dataengineering.
- **Exit criteria:** 200+ upvotes on HN, 50+ comments

### 8.3 Discord community
- **Status:** 🟡 High
- **Work:** Discord server. Help channels. Feature requests. Show-and-tell.
- **Exit criteria:** 100+ members in first month

### 8.4 Case studies
- **Status:** 🟢 Medium
- **Work:** Beta user case studies. "How [Company] migrated from dbt to briq in 1 day."
- **Exit criteria:** 3 published case studies

### 8.5 Content marketing
- **Status:** 🟢 Medium
- **Work:** Blog posts: "10 reasons pure SQL wins", "dbt migration guide", "SQL best practices for data teams". LinkedIn targeting FP&A/RevOps.
- **Exit criteria:** 50+ subscribers to briq blog

---

## Success Criteria Summary

### MVP (End of Phase 1)
- [ ] `briq build` works with parallel execution
- [ ] 4+ warehouse adapters tested
- [ ] Model selection with `+`/`-` notation
- [ ] Schema drift detection
- [ ] Column-level lineage in docs

### Beta (End of Phase 4)
- [ ] dbt projects import fully (SQL + YAML tests + sources)
- [ ] GitHub Action for CI/CD
- [ ] Airflow integration (`briq-airflow` package published, example DAGs documented)
- [ ] Published on PyPI
- [ ] 90%+ dbt project compatibility
- [ ] 50+ unit/integration tests passing

### Public Launch (End of Phase 5)
- [ ] Open source on GitHub
- [ ] Documentation site live
- [ ] VS Code extension on marketplace
- [ ] briq-utils package published
- [ ] Hacker News launch post

### Revenue (End of Phase 6)
- [ ] Studio Pro paying users
- [ ] 100+ Studio signups
- [ ] First Cloud customer

### Scale (End of Phase 7)
- [ ] Enterprise customer
- [ ] SOC 2 certified
- [ ] 1,000+ GitHub stars
- [ ] 500+ Discord members

---

*This roadmap is a living document. Priorities shift based on user feedback and market conditions. But the destination is fixed: make briq the best way to build data models for everyone who writes SQL.*
