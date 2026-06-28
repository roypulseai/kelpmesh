# Column Masking

Inject SQL-level column masking based on sensitivity and user role. Masks are applied at query time — base tables remain unmasked for admin access.

## Role Hierarchy

```
viewer → editor → admin
```

## Default Access

| Role | Can See |
|------|---------|
| viewer | internal only |
| editor | internal, restricted |
| admin | internal, restricted, sensitive, pii |

## Masking Strategies

| Sensitivity | Columns | Strategy |
|-------------|---------|----------|
| **pii** | email | `regexp_replace(col, '(.).*@(.*)', '\1***@\2')` |
| **pii** | phone | `regexp_replace(col, '(\d{3})\d{4}(\d{2})', '\1****\2')` |
| **pii** | default | `concat(left(col, 2), '****')` |
| **sensitive** | credit_card | `concat('****-****-****-', right(col, 4))` |
| **sensitive** | default | `'[REDACTED - SENSITIVE]'` |
| **restricted** | default | `'[REDACTED - RESTRICTED]'` |

## CLI Usage

```bash
# Preview masking for a role
briq security mask --table users --columns email,phone,ssn --role viewer
```
