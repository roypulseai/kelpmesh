# Testing

KelpMesh has a built-in test framework for asserting data quality in your warehouse. Tests are SQL files that return rows when something is wrong and return zero rows when everything is fine.

---

## Writing tests

A test is a `SELECT` query. If it returns any rows, the test fails.

```sql
-- tests/assert_no_negative_amounts.sql
SELECT COUNT(*) AS failures
FROM orders
WHERE amount < 0
HAVING COUNT(*) > 0
```

Run all tests:

```bash
kelpmesh test
```

Run a single test:

```bash
kelpmesh test --select assert_no_negative_amounts
```

---

## Generic tests in schema.yml

Common tests can be declared inline in your `schema.yml` without writing SQL:

```yaml
models:
  - name: orders
    columns:
      - name: order_id
        tests:
          - not_null
          - unique
      - name: customer_id
        tests:
          - not_null
          - relationships:
              to: customers
              field: id
      - name: status
        tests:
          - accepted_values:
              values: ["pending", "shipped", "cancelled", "refunded"]
      - name: amount
        tests:
          - not_null
```

### Built-in generic tests

| Test | What it checks |
|---|---|
| `not_null` | Column has no NULL values |
| `unique` | Column has no duplicate values |
| `accepted_values` | All values are in the provided list |
| `relationships` | Every value exists in the referenced table/column |

---

## Test severity

Mark a test as a warning instead of a failure so the run continues:

```yaml
- name: amount
  tests:
    - not_null:
        severity: warn
```

| Severity | Behaviour |
|---|---|
| `error` (default) | Test failure stops the run and exits non-zero |
| `warn` | Test failure is logged but the run continues |

---

## Data freshness

Assert that a source table has been updated recently:

```yaml
sources:
  - name: raw
    tables:
      - name: orders
        freshness:
          warn_after: { count: 6, period: hour }
          error_after: { count: 24, period: hour }
        loaded_at_field: _loaded_at
```

```bash
KelpMesh source freshness
```

---

## Continuous integration

Run tests automatically in CI to gate merges:

```yaml
# .github/workflows/kelpmesh.yml
- name: kelpmesh test
  run: kelpmesh build  # build = run + test
  env:
    KELPMESH_WAREHOUSE_PASSWORD: ${{ secrets.WAREHOUSE_PASSWORD }}
```

A non-zero exit code from `kelpmesh test` will fail the CI job.

---

## Best practices

- Name test files with the `assert_` prefix for clarity (`assert_no_orphan_orders.sql`).
- Test every `NOT NULL` constraint and every `unique_key` used in incremental models.
- Add `accepted_values` tests for status/enum columns — they catch upstream schema changes early.
- Run `kelpmesh build` (run + test) in CI on every pull request.
- For large tables, use `LIMIT 1` in tests instead of `COUNT(*)` — it's faster and still catches violations.
