# Secrets Scanning

Detect hardcoded credentials and secrets in SQL files and configuration.

## Scan Patterns

13 pattern types are detected:

- passwords, secret keys, API keys, tokens
- connection strings, private keys, AWS keys
- PEM private keys
- JDBC / Postgres / MySQL / Snowflake URLs with credentials
- Environment variable fallback values

## CLI Usage

```bash
# Scan default paths (models/)
kelpmesh scan secrets

# Scan all file types including config
kelpmesh scan secrets --all

# Fail CI if secrets found
kelpmesh scan secrets --fail

# Scan specific file or directory
kelpmesh scan secrets ./config/

# Generate encryption key
kelpmesh scan generate-key
```

## Ignore false positives

Add `-- KelpMesh:scan-ignore` to any line to suppress detection:

```sql
SELECT * FROM users  -- KelpMesh:scan-ignore
WHERE password = 'test123'
```

## CI Integration

```yaml
# .github/workflows/ci.yml
- name: Scan for secrets
  run: kelpmesh scan secrets --fail
```
