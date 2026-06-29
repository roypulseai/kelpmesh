"""Example DAG: auto-generated DAG from kelpmesh project model layers."""
from kelpmesh_airflow.dags import KelpMeshDag

dag = KelpMeshDag(
    dag_id="kelpmesh_auto_dag",
    project_dir="/path/to/kelpmesh_project",
    schedule="@daily",
)
