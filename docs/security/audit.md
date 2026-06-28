# Audit Logging

KelpMesh records every CLI and API action in an append-only JSONL audit log, providing a tamper-evident trail for compliance.

## Location

The audit log is stored at `target/audit.log` in your project directory.

## Format

Each line is a JSON object:

```json
{
  "id": "a1b2c3d4e5f6",
  "timestamp": "2026-06-27T12:00:00.000000Z",
  "action": "model.run",
  "actor": "cli",
  "resource": "model:orders",
  "status": "success",
  "before": null,
  "after": {"rows": 100},
  "detail": "Rows: 100"
}
```

## Actions tracked

- `run` — project execution start
- `model.run` — individual model execution (success/failure with row counts)
- `pii_erase` — PII erasure operations
- `pii_erase.dry_run` — dry-run PII erasure
- Any custom action via the API

## CLI Usage

```bash
# View recent audit entries
KelpMesh security audit

# Filter by actor
KelpMesh security audit --actor admin

# Filter by action
KelpMesh security audit --action model.run

# Filter by status
KelpMesh security audit --status failed

# Limit entries
KelpMesh security audit --limit 10
```
