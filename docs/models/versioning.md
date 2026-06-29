# Model Versioning

Model versioning allows you to make breaking changes to a model's interface without immediately breaking downstream consumers. Both the old and new versions coexist in the warehouse until the old one is deprecated.

## The Problem

Renaming a column in `orders` breaks every model that references it. Without versioning, you must:
1. Rename the column in `orders`
2. Update every downstream model in the same PR
3. Hope nothing breaks in production

With versioning, you introduce `orders` v2 alongside v1. Downstream teams migrate at their own pace.

## Declare a Versioned Model

Create a new file `models/orders_v2.sql`:

```sql
-- version: 2
-- defined_in: orders
-- materialized: table
-- contract: true

SELECT
    id            AS order_id,       -- renamed from "id"
    customer_id,
    total_cents / 100.0 AS amount,   -- type changed from integer cents to decimal
    order_status  AS status,         -- renamed from "order_status"
    placed_at     AS created_at      -- renamed from "placed_at"
FROM raw_orders
```

The original `models/orders.sql` becomes v1 implicitly (or you can add `-- version: 1`).

## Physical Table Names

| Model file | `version` | Physical table |
|-----------|-----------|----------------|
| `orders.sql` | (none) | `orders` (latest alias) |
| `orders_v2.sql` | `2` | `orders_v2` |
| `orders_v1.sql` | `1` | `orders_v1` |

The `orders` table is automatically aliased to the latest version's table (v2 in this case) so existing `ref('orders')` calls continue to work.

## ref() with Version

```sql
-- Resolves to the LATEST version (v2)
SELECT * FROM ref('orders')

-- Resolves to v1 specifically
SELECT * FROM ref('orders', version=1)

-- Resolves to v2 specifically
SELECT * FROM ref('orders', version=2)
```

## Deprecation Workflow

1. **Introduce v2** — create `orders_v2.sql`, add contract
2. **Announce** — notify downstream teams of the migration
3. **Migrate downstream** — teams update `ref('orders')` calls or use `ref('orders', version=2)`
4. **Deprecate v1** — add `-- enabled: false` to `orders_v1.sql` after all consumers migrate
5. **Delete v1** — remove the file after the deprecation period

## schema.yml for Versioned Models

```yaml
models:
  - name: orders_v2
    description: "Orders v2 — renamed columns for clarity"
    config:
      version: 2
      defined_in: orders
      latest_version: 2
      materialized: table
    columns:
      - name: order_id
        data_type: INTEGER
      - name: amount
        data_type: DOUBLE
```

## Run a Specific Version

```bash
# Run only the latest version
kelpmesh run orders

# Run a specific version
kelpmesh run orders_v2

# Run all versions of a model
kelpmesh run --select orders+
```
