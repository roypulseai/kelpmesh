# Migration from dbt

KelpMesh can automatically convert dbt projects to pure SQL.

## Import

```bash
KelpMesh import ./dbt-project --output ./KelpMesh-project
```

This converts:

- **Models** — Jinja `{{ ref() }}` → pure SQL table references, `{{ config() }}` → materialization settings
- **SQL tests** — converted as-is
- **Schema.yml tests** — not_null, unique, accepted_values, relationships
- **Sources** — mapped to direct table references
- **Seeds** — copied as SQL files
- **Snapshots** — converted to views
- **Analyses** — copied as-is

## Row-by-row comparison

During migration, compare KelpMesh output against dbt:

```bash
KelpMesh compare --model orders --dbt ../dbt-project
```

## Why migrate?

| Feature | dbt | KelpMesh |
|---------|-----|------|
| Model syntax | Jinja-templated SQL | Pure SQL |
| Column lineage | Enterprise only | Free |
| Schema drift | Manual | Built-in |
| Audit logging | Not included | Built-in |
| Security features | Not included | Built-in suite |
| AI assistant support | Broken | Full |
| Learning curve | Weeks | Minutes |
