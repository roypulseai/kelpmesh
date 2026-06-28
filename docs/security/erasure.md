# PII Erasure

Right to be forgotten — erase PII across warehouse tables for a given identifier.

## How it works

1. Scans warehouse tables for PII-classified columns
2. Generates `UPDATE` statements to NULL out PII values
3. Adds a `_pii_erased_at` metadata column for auditability
4. Records every erasure in the audit log

## CLI Usage

```bash
# Dry run — see what would be erased
briq security clean-pii --id-col email --id-value user@example.com --dry-run

# Execute erasure
briq security clean-pii --id-col email --id-value user@example.com

# Erase from specific tables only
briq security clean-pii --id-col email --id-value user@example.com --tables users,orders
```
