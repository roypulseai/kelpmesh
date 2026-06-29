"""Run history — record and query historical run outcomes."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
import duckdb
import threading


class RunHistory:
    """Persistent store for per-model run outcomes across kelpmesh sessions.

    Stored in ``target/kelpmesh_run_history.duckdb`` alongside the state DB so
    it survives across invocations and can be queried independently.
    """

    def __init__(self, project_path: Path):
        db_path = project_path / "target" / "kelpmesh_run_history.duckdb"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(db_path))
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id     VARCHAR,
                model_name VARCHAR,
                status     VARCHAR,
                started_at TIMESTAMP,
                elapsed_s  DOUBLE,
                row_count  INTEGER DEFAULT 0,
                error_msg  VARCHAR,
                env        VARCHAR DEFAULT 'default'
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS runs_model ON runs (model_name)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS runs_started ON runs (started_at DESC)"
        )

    def record(
        self,
        run_id: str,
        model_name: str,
        status: str,
        started_at: datetime,
        elapsed_s: float,
        row_count: int = 0,
        error_msg: str | None = None,
        env: str = "default",
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO runs
                    (run_id, model_name, status, started_at, elapsed_s, row_count, error_msg, env)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [run_id, model_name, status, started_at, elapsed_s, row_count, error_msg, env],
            )

    def get_history(
        self,
        model_name: str | None = None,
        limit: int = 20,
        env: str | None = None,
    ) -> list[dict]:
        clauses = []
        params: list = []
        if model_name:
            clauses.append("model_name = ?")
            params.append(model_name)
        if env:
            clauses.append("env = ?")
            params.append(env)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"""
            SELECT run_id, model_name, status, started_at, elapsed_s, row_count, error_msg, env
            FROM runs {where}
            ORDER BY started_at DESC
            LIMIT ?
            """,
            params + [limit],
        ).fetchall()
        return [
            {
                "run_id": r[0],
                "model_name": r[1],
                "status": r[2],
                "started_at": r[3].isoformat() if r[3] else None,
                "elapsed_s": r[4],
                "row_count": r[5],
                "error_msg": r[6],
                "env": r[7],
            }
            for r in rows
        ]

    def rolling_row_counts(self, model_name: str, n: int = 7) -> list[int]:
        """Return the last *n* row counts for *model_name* (oldest first)."""
        rows = self._conn.execute(
            """
            SELECT row_count FROM runs
            WHERE model_name = ? AND status = 'success'
            ORDER BY started_at DESC
            LIMIT ?
            """,
            [model_name, n],
        ).fetchall()
        return [r[0] for r in reversed(rows)]

    def close(self):
        self._conn.execute("CHECKPOINT")
        self._conn.close()
