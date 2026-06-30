# Pre-commit

Add KelpMesh validation to your pre-commit hooks:

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/RoyPulseAI/kelpmesh
  rev: v0.2.0
  hooks:
    - id: KelpMesh-validate
```

This validates SQL files and detects circular dependencies in your model graph.
