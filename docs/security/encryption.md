# Encryption

KelpMesh supports transparent Fernet encryption (AES-128-CBC + HMAC-SHA256) for project state and DuckDB databases.

## Setup

```bash
# Generate an encryption key
kelpmesh scan generate-key

# Initialize a project with encryption
kelpmesh init my_project --encrypt
```

## Environment Variable

Set the `KELPMESH_ENCRYPTION_KEY` environment variable:

```bash
# Linux/macOS
export KELPMESH_ENCRYPTION_KEY=your-generated-key-here

# Windows
set KELPMESH_ENCRYPTION_KEY=your-generated-key-here
```

## How it works

1. When `KELPMESH_ENCRYPTION_KEY` is set and DuckDB >= 1.0 is available, the state database is encrypted at rest
2. The state database (`target/kelpmesh_state.duckdb`) is transparently encrypted on close and decrypted on open
3. Encryption uses Fernet (AES-128-CBC + HMAC-SHA256) via the `cryptography` package

## Verify encryption

```bash
kelpmesh debug
# Look for: Encryption key: (set)
```
