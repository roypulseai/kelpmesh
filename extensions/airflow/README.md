# KelpMesh Airflow Integration

Apache Airflow operators and helpers for orchestrating KelpMesh projects.

## Installation

```bash
pip install KelpMesh-airflow
```

## Usage

### KelpMeshOperator

Run `kelpmesh build` as an Airflow task:

```python
from airflow import DAG
from kelpmesh_airflow.operators import KelpMeshOperator
from datetime import datetime

with DAG("kelpmesh_daily", start_date=datetime(2024, 1, 1), schedule="@daily") as dag:
    build = KelpMeshOperator(
        task_id="kelpmesh_build",
        kelpmesh_cmd="build",
        project_dir="/path/to/project",
    )
```

### KelpMeshDag

Auto-generate an Airflow DAG from a KelpMesh project's model DAG:

```python
from kelpmesh_airflow.dags import KelpMeshDag

dag = KelpMeshDag(
    dag_id="kelpmesh_models",
    project_dir="/path/to/project",
    schedule="@daily",
)
```

### Deferrable Operator

For long-running models, use the deferrable operator:

```python
KelpMeshOperator(
    task_id="kelpmesh_build",
    kelpmesh_cmd="build",
    project_dir="/path/to/project",
    deferrable=True,
)
```
