# GitHub Actions

Use the `KelpMesh-build` GitHub Action to run models and tests on every PR:

```yaml
# .github/workflows/ci.yml
name: kelpmesh CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install KelpMesh
      - run: kelpmesh build
      - run: kelpmesh scan secrets --fail
```
