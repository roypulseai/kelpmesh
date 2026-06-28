# GitLab CI

Copy the template from `ci/gitlab.yml` into your project:

```yaml
# .gitlab-ci.yml
stages:
  - build

briq-build:
  stage: build
  image: python:3.11
  script:
    - pip install briq
    - briq build
    - briq scan secrets --fail
```
