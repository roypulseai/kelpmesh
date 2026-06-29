# Model Contracts

Model contracts enforce that a model's output exactly matches its declared schema. When a contract is violated, the run fails immediately — protecting downstream consumers from silent schema drift.

## Declare a Contract

Add `contract: enforced: true` to a model's entry in `schema.yml`, along with column definitions:

```yaml
models:
  - name: orders
    description: "Cleaned orders table — stable API for downstream models"
    contract:
      enforced: true
      constrained_columns: false  # true = fail on extra columns too
    columns:
      - name: order_id
        data_type: INTEGER
        description: "Unique order identifier"
        tests:
          - not_null
          - unique
      - name: customer_id
        data_type: INTEGER
        tests:
          - not_null
      - name: amount
        data_type: DOUBLE
      - name: status
        data_type: VARCHAR
      - name: created_at
        data_type: TIMESTAMP
```

Or declare in the model header:
```sql
-- contract: true

SELECT
    order_id::INTEGER,
    customer_id::INTEGER,
    amount::DOUBLE,
    status::VARCHAR,
    created_at::TIMESTAMP
FROM raw_orders
```

## What is Checked

After every model run, KelpMesh fetches the warehouse schema and validates:

1. **Missing columns** — a column declared in the contract is absent from the table
2. **Type mismatches** — `INTEGER` declared but `VARCHAR` in warehouse (normalised aliases — `INT`, `INT4`, `INTEGER` are all equivalent)
3. **Extra columns** (only when `constrained_columns: true`) — columns in the table not declared in the contract

## Type Aliases

KelpMesh normalises type names before comparing, so these are all equivalent:

| Canonical | Aliases |
|-----------|---------|
| `INTEGER` | `INT`, `INT4`, `INT32`, `SIGNED` |
| `BIGINT` | `INT8`, `INT64`, `LONG` |
| `VARCHAR` | `TEXT`, `STRING`, `CHAR` |
| `DOUBLE` | `FLOAT8`, `NUMERIC`, `DECIMAL` |
| `BOOLEAN` | `BOOL`, `LOGICAL` |
| `TIMESTAMP` | `DATETIME` |

## Contract Violation Behaviour

When a contract is violated, `kelpmesh run` prints the violations and exits with code 1:

```
Error: Contract violation: [orders] column 'amount' type mismatch: expected 'DOUBLE', got 'VARCHAR'
```

To investigate:
```bash
kelpmesh compile orders --print
kelpmesh run orders --debug
```

## Best Practices

**Use contracts on "interface models"** — models that many other models depend on. These are the ones where a silent schema change would cause widespread breakage.

**Pair with model versioning** for breaking changes:
```sql
-- version: 2
-- defined_in: orders
-- contract: true
```

**CI enforcement** — contracts run automatically as part of `kelpmesh build` and `kelpmesh run`. In CI, a contract violation blocks the PR.

**Don't over-constrain** — `constrained_columns: false` (the default) allows adding new columns without breaking the contract. Set it to `true` only on very stable models.
