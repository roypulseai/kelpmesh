# Airflow

Install the KelpMesh Airflow integration:

```bash
pip install KelpMesh-airflow
```

Use `BriqOperator` to run KelpMesh commands as Airflow tasks:

```python
from kelpmesh_airflow.operators import BriqOperator

BriqOperator(
    task_id="briq_build",
    briq_cmd="build",
    project_dir="/path/to/project",
)
```

Use `BriqDag` to auto-generate Airflow DAGs from your model dependency graph.
