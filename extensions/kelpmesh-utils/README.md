# KelpMesh-utils

Essential utility macros for KelpMesh: `surrogate_key`, `date_spine`, `group_by`, `pivot`, `unpivot`.

## Installation

```bash
KelpMesh deps add KelpMesh-utils --source ./extensions/KelpMesh-utils
KelpMesh deps install
```

## Usage

Reference models by name in your SQL:

```sql
-- Using the surrogate key pattern in a model
SELECT md5(CONCAT(id, '-', name)) AS unique_id, *
FROM my_source
```
