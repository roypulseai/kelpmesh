# briq Mesh

briq Mesh enables cross-project model references. Multiple briq projects in a monorepo or workspace can reference each other's models as if they were local, with access controls and producer contracts to enforce governance.

---

## When to use Mesh

- You have multiple teams each owning their own briq project
- A downstream project (e.g. a BI mart) needs to reference a model from an upstream platform project
- You want to enforce that upstream models expose a stable, versioned interface

---

## Workspace layout

```
acme/
├── mesh.yml          # Workspace-level config
├── platform/         # Upstream project (producer)
│   ├── briq.yml
│   ├── models/
│   │   └── dim_customers.sql
│   └── interface.yml # Published contract
└── analytics/        # Downstream project (consumer)
    ├── briq.yml
    └── models/
        └── customer_orders.sql
```

---

## mesh.yml

```yaml
mesh:
  name: acme_mesh
  projects:
    - name: platform
      path: ./platform
      warehouse: duckdb
      group: platform
      default_access: protected

    - name: analytics
      path: ./analytics
      warehouse: duckdb
      group: analytics
      default_access: private
```

---

## Cross-project references

Reference another project's model using the `project__model` double-underscore convention:

```sql
-- analytics/models/customer_orders.sql
SELECT
  c.customer_id,
  c.email,
  COUNT(o.order_id) AS order_count
FROM platform__dim_customers AS c        -- cross-project ref
JOIN local_orders AS o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.email
```

briq automatically rewrites `platform__dim_customers` to the resolved table name in the platform project's warehouse.

---

## Access levels

Control which projects can reference a model by setting `access:` in `schema.yml`:

```yaml
models:
  - name: dim_customers
    access: public       # any project can reference

  - name: internal_costs
    access: protected    # same group only

  - name: raw_payments
    access: private      # cannot be referenced cross-project
```

| Level | Who can reference |
|---|---|
| `public` | Any project in the mesh |
| `protected` | Projects in the same `group` only |
| `private` | No cross-project references allowed |

---

## Producer contracts (interface.yml)

Upstream projects publish a contract listing the columns and access levels they commit to maintaining:

```yaml
# platform/interface.yml
version: 1
models:
  - name: dim_customers
    access: public
    columns:
      - name: customer_id
        type: VARCHAR
      - name: email
        type: VARCHAR
      - name: created_at
        type: TIMESTAMP
```

Validate that the current code still honours the contract:

```bash
briq mesh validate
```

This reports violations:
- `missing_column` — a committed column was removed
- `model_removed` — a published model no longer exists
- `access_downgrade` — a model's access was tightened (e.g. `public` → `private`)

---

## CLI reference

```bash
# Initialise mesh.yml in the current workspace
briq mesh init

# Show health status of all projects
briq mesh status

# Validate all contracts
briq mesh validate

# Print the cross-project dependency graph (JSON)
briq mesh graph

# Publish updated interface.yml from a project's schema.yml
briq mesh publish --project platform
```

`briq mesh validate` exits with code 1 if any violations are found, making it suitable for CI gating.

---

## Health report

`briq mesh status` returns a health summary for each project:

```
✓ platform   healthy   3 models, 0 violations
⚠ analytics  warn      1 stale cross-ref (platform__dim_customers not found)
✗ reporting  error     mesh.yml missing project path
```

| Status | Meaning |
|---|---|
| `healthy` | All refs resolved, no contract violations |
| `warn` | Unresolved refs or stale interface |
| `error` | Project path missing or unreachable |
| `missing` | Project declared in mesh.yml but directory not found |
