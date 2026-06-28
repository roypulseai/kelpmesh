"""kelpmesh Studio scheduling engine — cron + dependency-based triggers."""
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text


def _get_engine():
    """Create a separate engine for scheduler access."""
    import os
    db_url = os.environ.get(
        "KELPMESH_STUDIO_DATABASE_URL",
        f"sqlite:///{Path(__file__).parent.parent / 'studio_data' / 'studio.db'}",
    )
    connect_args = {} if db_url.startswith("postgresql") else {"check_same_thread": False}
    return create_engine(db_url, connect_args=connect_args)


def list_schedules() -> list[dict]:
    engine = _get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT project_name, cron, depends_on, enabled FROM schedules")
        ).fetchall()
    return [
        {
            "project": r[0],
            "cron": r[1] or "",
            "depends_on": r[2] or [],
            "enabled": bool(r[3]),
        }
        for r in rows
    ]


def set_schedule(project_name: str, cron: str = "", depends_on: list[str] | None = None, enabled: bool = True):
    engine = _get_engine()
    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM schedules WHERE project_name = :p"),
            {"p": project_name},
        ).fetchone()
        if existing:
            conn.execute(
                text("UPDATE schedules SET cron = :c, depends_on = :d, enabled = :e WHERE project_name = :p"),
                {"c": cron, "d": depends_on or [], "e": 1 if enabled else 0, "p": project_name},
            )
        else:
            conn.execute(
                text("INSERT INTO schedules (project_name, cron, depends_on, enabled) VALUES (:p, :c, :d, :e)"),
                {"p": project_name, "c": cron, "d": depends_on or [], "e": 1 if enabled else 0},
            )
        conn.commit()


def remove_schedule(project_name: str):
    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM schedules WHERE project_name = :p"), {"p": project_name})
        conn.commit()


def _last_success(project_name: str, db_path: Path) -> datetime | None:
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT created_at FROM run_history WHERE project_name = :p AND success = 1 ORDER BY created_at DESC LIMIT 1"),
            {"p": project_name},
        ).fetchone()
    if row:
        val = row[0]
        if isinstance(val, str):
            return datetime.fromisoformat(val)
        return val
    return None


def dependencies_satisfied(project_name: str) -> dict:
    schedules = list_schedules()
    entry = next((s for s in schedules if s["project"] == project_name), None)
    deps = entry.get("depends_on", []) if entry else []
    results = {}
    for dep in deps:
        last = _last_success(dep, Path())
        results[dep] = {"ok": last is not None, "last_success": str(last) if last else None}
    return {
        "project": project_name,
        "dependencies": deps,
        "all_satisfied": all(r["ok"] for r in results.values()),
        "results": results,
    }


def _should_run(project_name: str, cfg: dict) -> bool:
    deps = cfg.get("depends_on", [])
    if not deps:
        return True
    for dep in deps:
        last = _last_success(dep, Path())
        if last is None:
            return False
    return True


def run_scheduler():
    """Scheduler loop — runs every 60s."""
    def _loop():
        while True:
            try:
                schedules = list_schedules()
                for entry in schedules:
                    if not entry.get("enabled"):
                        continue
                    if not _should_run(entry["project"], entry):
                        continue

                    from kelpmesh.core.project import Project
                    from kelpmesh.core.executor import Executor
                    from kelpmesh.state.engine import StateEngine
                    from kelpmesh.adapters import get_adapter

                    data_dir = Path(
                        __file__).parent.parent / "studio_data"
                    project_path = data_dir / entry["project"]
                    if not (project_path / "kelpmesh.yml").exists():
                        continue

                    project = Project(project_path)
                    adapter = get_adapter(project.config.warehouse, project_path=str(project_path))
                    state = StateEngine(project.path)
                    executor = Executor(project, adapter, state)
                    results = executor.run()
                    adapter.disconnect()
                    state.close()

                    engine = _get_engine()
                    success = 1 if len(results.get("failed", [])) == 0 else 0
                    with engine.connect() as conn:
                        conn.execute(
                            text("INSERT INTO run_history (project_name, success, models_ran, models_failed, created_at) VALUES (:p, :s, :r, :f, :t)"),
                            {
                                "p": entry["project"],
                                "s": success,
                                "r": len(results.get("ran", [])),
                                "f": len(results.get("failed", [])),
                                "t": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                        conn.commit()
            except Exception:
                pass
            time.sleep(60)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
