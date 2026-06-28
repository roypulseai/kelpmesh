# Show HN: briq – pure SQL data transformation, no Jinja required

briq is an open-source alternative to dbt that uses **pure SQL** instead of Jinja-templated SQL.

**No Jinja. No macros. Just SQL.**

```sql
-- This is valid briq. Dependencies resolved by parsing the AST.
SELECT customer_id, SUM(amount) AS total FROM orders GROUP BY 1
```

Why this matters: dbt forced analysts to learn Jinja templating embedded inside SQL. This breaks IDE intellisense, AI coding assistants (Copilot/Cursor can't parse Jinja-templated SQL), SQL linters, and code review. Every `{{ ref('model') }}` and `{{ config(...) }}` block makes the SQL harder to read, review, and maintain.

briq's approach: dependency resolution via AST parsing. Your SQL is valid, portable SQL. Nothing more.

**What ships in 0.2:**

- Column-level lineage (free, not enterprise-locked)
- 6 warehouses: DuckDB, Snowflake, BigQuery, Postgres, Databricks, Microsoft Fabric
- Security suite: audit logging, RLS, column masking, data classification, PII erasure, secrets scanning, transparent encryption
- dbt migration: `briq import ./dbt-project --output ./briq-project`
- No telemetry (zero phone-home, enforced at code level)
- 27 CLI commands

```bash
pip install briq
briq init my_project
briq run
```

License: Apache 2.0

https://github.com/briq-dev/briq
