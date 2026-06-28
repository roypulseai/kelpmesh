"""Example DAG: auto-generated DAG from briq project model layers."""
from briq_airflow.dags import BriqDag

dag = BriqDag(
    dag_id="briq_auto_dag",
    project_dir="/path/to/briq_project",
    schedule="@daily",
)
