# briq Airflow Integration

Apache Airflow operators and helpers for orchestrating briq projects.

## Installation

```bash
pip install briq-airflow
```

## Usage

### BriqOperator

Run `briq build` as an Airflow task:

```python
from airflow import DAG
from briq_airflow.operators import BriqOperator
from datetime import datetime

with DAG("briq_daily", start_date=datetime(2024, 1, 1), schedule="@daily") as dag:
    build = BriqOperator(
        task_id="briq_build",
        briq_cmd="build",
        project_dir="/path/to/project",
    )
```

### BriqDag

Auto-generate an Airflow DAG from a briq project's model DAG:

```python
from briq_airflow.dags import BriqDag

dag = BriqDag(
    dag_id="briq_models",
    project_dir="/path/to/project",
    schedule="@daily",
)
```

### Deferrable Operator

For long-running models, use the deferrable operator:

```python
BriqOperator(
    task_id="briq_build",
    briq_cmd="build",
    project_dir="/path/to/project",
    deferrable=True,
)
```
