"""Example DAG: auto-generated DAG from kelpmesh project model layers."""
from kelpmesh_airflow.dags import BriqDag

dag = BriqDag(
    dag_id="briq_auto_dag",
    project_dir="/path/to/briq_project",
    schedule="@daily",
)
