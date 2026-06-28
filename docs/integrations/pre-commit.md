# Pre-commit

Add briq validation to your pre-commit hooks:

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/briq-dev/briq
  rev: v0.2.0
  hooks:
    - id: briq-validate
```

This validates SQL files and detects circular dependencies in your model graph.
