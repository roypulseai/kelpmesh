# Security Overview

briq includes a comprehensive security subsystem designed for enterprise compliance, including nFADP (Swiss law), GDPR, and SOC 2 requirements.

## Subsystems

| Feature | CLI Command | Description |
|---------|-------------|-------------|
| Audit Logging | `briq security audit` | Append-only JSONL audit trail |
| Data Classification | `briq security classify` | Tag columns as pii/sensitive/restricted/internal |
| Column Masking | `briq security mask` | SQL-level masking per role |
| Row-Level Security | `briq security rls` | Policy-based row filters per role |
| PII Erasure | `briq security clean-pii` | Right to be forgotten |
| Secrets Scanning | `briq scan secrets` | Detect hardcoded credentials |
| Encryption | `briq init --encrypt` | AES-256-GCM transparent encryption |
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
briq scan secrets --fail

# Initialize classification rules
briq security classify --init

# View audit log
briq security audit

# Check security status
briq security status
```
