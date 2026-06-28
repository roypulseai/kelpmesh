# Quickstart

## 1. Create a project

```bash
kelpmesh init my_project
cd my_project
```

This creates:

```
my_project/
├── kelpmesh.yml          # Project configuration
├── models/           # SQL model directory
│   └── example.sql   # Sample model
├── tests/            # SQL test directory
└── target/           # Output directory (generated)
```

## 2. Add seed data

```sql
-- seed.sql
INSERT INTO customers VALUES
  (1, 'Alice', 'alice@example.com'),
  (2, 'Bob', 'bob@example.com');
```

```bash
kelpmesh seed seed.sql
```

## 3. Write a model

```sql
-- models/orders.sql
SELECT
  customer_id,
  COUNT(*) AS order_count,
  SUM(amount) AS total_spent
FROM orders
GROUP BY customer_id
```

Dependencies between models are resolved automatically by parsing the SQL AST.

## 4. Run models

```bash
kelpmesh run
```

## 5. Test

```sql
-- tests/assert_orders_positive.sql
SELECT COUNT(*) AS failures
FROM orders
WHERE amount <= 0
HAVING COUNT(*) > 0
```

```bash
kelpmesh test
```

## 6. Build (run + test)

```bash
kelpmesh build
```

## 7. Generate docs

```bash
kelpmesh docs
```
