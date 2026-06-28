# Scan Commands

## kelpmesh scan secrets

Scan SQL files and configuration for hardcoded secrets and credentials.

```bash
kelpmesh scan secrets [path] [options]
```

Arguments:
- `path` — File or directory to scan (default: models/)

Options:
- `--all` — Scan all file types including YAML and config
- `--fail` — Exit with code 1 if secrets found (for CI)

## kelpmesh scan generate-key

Generate a random encryption key for the `KELPMESH_ENCRYPTION_KEY` environment variable.

```bash
kelpmesh scan generate-key
```

Outputs the key and instructions for setting it on Linux/macOS and Windows.
