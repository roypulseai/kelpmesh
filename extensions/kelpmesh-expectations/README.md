# KelpMesh-expectations

Data quality expectations for KelpMesh: uniqueness checks, accepted value sets, null checks, recency, cardinality.

## Installation

```bash
KelpMesh deps add KelpMesh-expectations --source ./extensions/KelpMesh-expectations
KelpMesh deps install
```

## Available Expectations

- `expect_column_unique` — values in a column are unique
- `expect_column_values_in_set` — values belong to an accepted set
- `expect_column_not_null` — column has no NULL values
- `expect_rowcount_equal` — two tables have the same row count
