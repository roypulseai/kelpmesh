"""Example DAG: daily kelpmesh build using BriqOperator."""
from datetime import datetime
from airflow import DAG
from kelpmesh_airflow.operators import BriqOperator

with DAG(
    "briq_daily_build",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    description="Daily kelpmesh build (run models + tests)",
) as dag:
    build = BriqOperator(
        task_id="briq_build",
        briq_cmd="build",
        project_dir="/path/to/briq_project",
    )
