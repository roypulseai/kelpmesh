# Security Commands

## briq security audit

View the append-only audit trail.

```bash
briq security audit [options]
```

Options:
- `--actor` — Filter by actor
- `--action` — Filter by action
- `--resource` — Filter by resource
- `--status` — Filter by status (success/failed)
- `--limit` — Number of entries (default: 100)

## briq security classify

Classify data columns by sensitivity level.

```bash
briq security classify [options]
```

Options:
- `--table` — Table to classify
- `--init` — Generate stub classify.yml

## briq security mask

Preview column masking for a role.

```bash
briq security mask [options]
```

Options:
- `--table` — Table name
- `--columns` — Comma-separated column names
- `--role` — Role to preview (viewer, editor, admin)

## briq security rls

List or generate row-level security policies.

```bash
briq security rls [options]
```

Options:
- `--init` — Generate stub security.yml

## briq security clean-pii

Erase PII data across warehouse tables.

```bash
briq security clean-pii [options]
```

Options:
- `--id-col` — Identifier column name
- `--id-value` — Identifier value to erase
- `--tables` — Comma-separated table names (all if omitted)
- `--dry-run` — Preview without erasing

## briq security status

Show security subsystem status.

```bash
briq security status
```

## briq security roles

List available roles and their access levels.

```bash
briq security roles
```
