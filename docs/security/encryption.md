# Encryption

briq supports transparent AES-256-GCM encryption for project state and DuckDB databases.

## Setup

```bash
# Generate an encryption key
briq scan generate-key

# Initialize a project with encryption
briq init my_project --encrypt
```

## Environment Variable

Set the `BRIQ_ENCRYPTION_KEY` environment variable:

```bash
# Linux/macOS
export BRIQ_ENCRYPTION_KEY=your-generated-key-here

# Windows
set BRIQ_ENCRYPTION_KEY=your-generated-key-here
```

## How it works

1. When `BRIQ_ENCRYPTION_KEY` is set and DuckDB >= 1.0 is available, the state database is encrypted at rest
2. The state database (`target/briq_state.duckdb`) is transparently encrypted on close and decrypted on open
3. Encryption uses Fernet (AES-256-GCM) via the `cryptography` package

## Verify encryption

```bash
briq debug
# Look for: Encryption key: (set)
```
