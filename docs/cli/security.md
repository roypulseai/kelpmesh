# Security Commands

## KelpMesh security audit

View the append-only audit trail.

```bash
KelpMesh security audit [options]
```

Options:
- `--actor` — Filter by actor
- `--action` — Filter by action
- `--resource` — Filter by resource
- `--status` — Filter by status (success/failed)
- `--limit` — Number of entries (default: 100)

## KelpMesh security classify

Classify data columns by sensitivity level.

```bash
KelpMesh security classify [options]
```

Options:
- `--table` — Table to classify
- `--init` — Generate stub classify.yml

## KelpMesh security mask

Preview column masking for a role.

```bash
KelpMesh security mask [options]
```

Options:
- `--table` — Table name
- `--columns` — Comma-separated column names
- `--role` — Role to preview (viewer, editor, admin)

## KelpMesh security rls

List or generate row-level security policies.

```bash
KelpMesh security rls [options]
```

Options:
- `--init` — Generate stub security.yml

## KelpMesh security clean-pii

Erase PII data across warehouse tables.

```bash
KelpMesh security clean-pii [options]
```

Options:
- `--id-col` — Identifier column name
- `--id-value` — Identifier value to erase
- `--tables` — Comma-separated table names (all if omitted)
- `--dry-run` — Preview without erasing

## KelpMesh security status

Show security subsystem status.

```bash
KelpMesh security status
```

## KelpMesh security roles

List available roles and their access levels.

```bash
KelpMesh security roles
```
