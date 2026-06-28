# Airflow

Install the briq Airflow integration:

```bash
pip install briq-airflow
```

Use `BriqOperator` to run briq commands as Airflow tasks:

```python
from briq_airflow.operators import BriqOperator

BriqOperator(
    task_id="briq_build",
    briq_cmd="build",
    project_dir="/path/to/project",
)
```

Use `BriqDag` to auto-generate Airflow DAGs from your model dependency graph.
