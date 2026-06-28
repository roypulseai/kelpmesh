# briq-utils

Essential utility macros for briq: `surrogate_key`, `date_spine`, `group_by`, `pivot`, `unpivot`.

## Installation

```bash
briq deps add briq-utils --source ./extensions/briq-utils
briq deps install
```

## Usage

Reference models by name in your SQL:

```sql
-- Using the surrogate key pattern in a model
SELECT md5(CONCAT(id, '-', name)) AS unique_id, *
FROM my_source
```
