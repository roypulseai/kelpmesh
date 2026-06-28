"""BriqDag — auto-generate Airflow DAGs from kelpmesh project model DAGs."""
from pathlib import Path
from airflow.models import DAG
from airflow.utils.task_group import TaskGroup
from kelpmesh_airflow.operators import BriqOperator


class BriqDag(DAG):
    """Auto-generate an Airflow DAG from a kelpmesh project's model DAG.

    Each kelpmesh dependency layer becomes an Airflow TaskGroup.
    Models within the same layer run in parallel.

    Args:
        dag_id: Airflow DAG ID.
        project_dir: Path to the kelpmesh project directory.
        schedule: Airflow schedule interval.
        start_date: Airflow start date.
        catchup: Whether to catch up on missed runs.
        full_refresh: If True, ignore cached state on each run.
        **kwargs: Additional Airflow DAG kwargs.
    """

    def __init__(
        self,
        dag_id: str,
        project_dir: str,
        schedule: str = "@daily",
        start_date=None,
        catchup: bool = False,
        full_refresh: bool = False,
        **kwargs,
    ):
        from datetime import datetime
        start = start_date or datetime(2024, 1, 1)

        super().__init__(
            dag_id=dag_id,
            schedule=schedule,
            start_date=start,
            catchup=catchup,
            **kwargs,
        )

        project_path = Path(project_dir).resolve()
        from kelpmesh.core.project import Project
        from kelpmesh.core.graph import DAGBuilder

        project = Project(project_path)
        dag_builder = DAGBuilder(project)
        layers = dag_builder.layers()

        prev_tasks = []
        for layer_idx, layer_models in enumerate(layers):
            with TaskGroup(
                group_id=f"layer_{layer_idx}",
                dag=self,
            ) as tg:
                tasks = []
                for model_name in layer_models:
                    task = BriqOperator(
                        task_id=f"briq_{model_name}",
                        briq_cmd="run",
                        project_dir=project_dir,
                        models=[model_name],
                        full_refresh=full_refresh,
                        dag=self,
                    )
                    tasks.append(task)
                    if prev_tasks:
                        for pt in prev_tasks:
                            pt >> task
                prev_tasks = tasks
