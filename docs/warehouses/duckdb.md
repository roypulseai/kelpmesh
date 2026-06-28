# DuckDB

The default warehouse for briq. No external dependencies required.

## Configuration

```yaml
warehouse:
  type: duckdb
  path: target/briq.duckdb  # or ":memory:" for in-memory
  database: my_db
  schema: main
  threads: 4
```

## Features

- Zero-configuration — no server, no credentials
- File-based or in-memory
- Transparent encryption via `BRIQ_ENCRYPTION_KEY`
- Connection pooling for parallel execution
