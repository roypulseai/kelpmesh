# Security Overview

KelpMesh includes a comprehensive security subsystem designed for enterprise compliance, including nFADP (Swiss law), GDPR, and SOC 2 requirements.

## Subsystems

| Feature | CLI Command | Description |
|---------|-------------|-------------|
| Audit Logging | `KelpMesh security audit` | Append-only JSONL audit trail |
| Data Classification | `KelpMesh security classify` | Tag columns as pii/sensitive/restricted/internal |
| Column Masking | `KelpMesh security mask` | SQL-level masking per role |
| Row-Level Security | `KelpMesh security rls` | Policy-based row filters per role |
| PII Erasure | `KelpMesh security clean-pii` | Right to be forgotten |
| Secrets Scanning | `kelpmesh scan secrets` | Detect hardcoded credentials |
| Encryption | `kelpmesh init --encrypt` | AES-256-GCM transparent encryption |
| Telemetry Guard | Built-in | Blocks telemetry/analytics packages |

## Role Hierarchy

```
viewer → editor → admin
```

- **viewer**: internal data only
- **editor**: internal + restricted
- **admin**: all data (internal, restricted, sensitive, pii)

## Quick Start

```bash
# Scan for secrets
kelpmesh scan secrets --fail

# Initialize classification rules
KelpMesh security classify --init

# View audit log
KelpMesh security audit

# Check security status
KelpMesh security status
```
