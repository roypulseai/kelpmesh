# GitHub Actions

Use the `briq-build` GitHub Action to run models and tests on every PR:

```yaml
# .github/workflows/ci.yml
name: briq CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install briq
      - run: briq build
      - run: briq scan secrets --fail
```
