# Data Classification

Classify columns by sensitivity level: `pii`, `sensitive`, `restricted`, or `internal`.

## Built-in Rules

KelpMesh includes 25 built-in column name rules:

| Classification | Columns |
|----------------|---------|
| **pii** | email, phone, mobile, ssn, passport, tax_id, national_id, address, birth_date, first_name, last_name, full_name |
| **sensitive** | credit_card, cvv, password_hash, token, api_key, salary, bonus, health, diagnosis |
| **restricted** | password, secret |

## Custom Rules

Create a `classify.yml` file in your project root to override or add rules:

```yaml
# classify.yml
users:
  email: pii
  phone: pii
  role: internal

orders:
  credit_card: sensitive
  amount: internal
  customer_email: pii
```

## CLI Usage

```bash
# Generate stub classify.yml
KelpMesh security classify --init

# Classify columns for a table
KelpMesh security classify --table users
```
