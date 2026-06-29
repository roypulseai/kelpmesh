# Airflow

Install the KelpMesh Airflow integration:

```bash
pip install KelpMesh-airflow
```

Use `KelpMeshOperator` to run KelpMesh commands as Airflow tasks:

```python
from kelpmesh_airflow.operators import KelpMeshOperator

KelpMeshOperator(
    task_id="kelpmesh_build",
    kelpmesh_cmd="build",
    project_dir="/path/to/project",
)
```

Use `KelpMeshDag` to auto-generate Airflow DAGs from your model dependency graph.
