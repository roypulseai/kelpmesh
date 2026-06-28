# GitLab CI

Copy the template from `ci/gitlab.yml` into your project:

```yaml
# .gitlab-ci.yml
stages:
  - build

KelpMesh-build:
  stage: build
  image: python:3.11
  script:
    - pip install KelpMesh
    - kelpmesh build
    - kelpmesh scan secrets --fail
```
