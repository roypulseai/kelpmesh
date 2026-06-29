"""Example DAG: daily kelpmesh build using KelpMeshOperator."""
from datetime import datetime
from airflow import DAG
from kelpmesh_airflow.operators import KelpMeshOperator

with DAG(
    "kelpmesh_daily_build",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    description="Daily kelpmesh build (run models + tests)",
) as dag:
    build = KelpMeshOperator(
        task_id="kelpmesh_build",
        kelpmesh_cmd="build",
        project_dir="/path/to/kelpmesh_project",
    )
