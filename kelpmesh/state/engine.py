"""State engine — tracks model state, supports deferral to production targets, WAL mode."""

import os
import tempfile
from pathlib import Path
import duckdb
from datetime import datetime
import threading

from kelpmesh.core.crypto import encrypt_file, decrypt_file, is_encrypted


def _open_state(db_path: Path, encryption_key: str | None = None, read_only: bool = False) -> tuple[duckdb.DuckDBPyConnection, Path | None]:
    """Open state DB, handling encryption. Returns (connection, tmp_path)."""
    use_encryption = bool(encryption_key or os.environ.get("KELPMESH_ENCRYPTION_KEY"))
    tmp_path = None

    if use_encryption and db_path.exists():
        raw = db_path.read_bytes()
        if is_encrypted(raw):
            decrypted = decrypt_file(db_path)
            if decrypted is None:
                raise RuntimeError("Failed to decrypt state database. Check KELPMESH_ENCRYPTION_KEY.")
            tmp_path = Path(tempfile.mktemp(suffix=".duckdb"))
            tmp_path.write_bytes(decrypted)
            conn = duckdb.connect(str(tmp_path), read_only=read_only)
        else:
            conn = duckdb.connect(str(db_path), read_only=read_only)
    else:
        conn = duckdb.connect(str(db_path), read_only=read_only)

    if not read_only:
        conn.execute("PRAGMA wal_autocheckpoint = '1GB'")

    return conn, tmp_path


class StateEngine:
    """Tracks model run state, hashes, row counts, and schema snapshots.

    Supports deferral: point at a production state DB to skip models
    whose hash matches the production version.
    """

    def __init__(self, project_path: Path, encryption_key: str | None = None):
        self.db_path = project_path / "target" / "kelpmesh_state.duckdb"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._use_encryption = bool(encryption_key or os.environ.get("KELPMESH_ENCRYPTION_KEY"))
        self._tmp_path = None

        self.conn, self._tmp_path = _open_state(self.db_path, encryption_key, read_only=False)
        self._init_schema()

    @classmethod
    def open_readonly(cls, db_path: Path, encryption_key: str | None = None) -> "StateEngine":
        """Open an existing state DB in read-only mode for deferral."""
        engine = cls.__new__(cls)
        engine.db_path = db_path
        engine._lock = threading.Lock()
        engine._use_encryption = bool(encryption_key or os.environ.get("KELPMESH_ENCRYPTION_KEY"))
        engine._tmp_path = None
        engine.conn, engine._tmp_path = _open_state(db_path, encryption_key, read_only=True)
        # Skip _init_schema — tables already exist in the production state DB
        return engine

    def _init_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS model_state (
                model_name VARCHAR PRIMARY KEY,
                hash VARCHAR,
                last_run_at TIMESTAMP,
                row_count INTEGER DEFAULT 0,
                metadata VARCHAR
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS run_history (
                id INTEGER PRIMARY KEY,
                run_id VARCHAR,
                model_name VARCHAR,
                status VARCHAR,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                rows_affected INTEGER DEFAULT 0
            )
        """)
        self.conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS run_history_seq
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_state (
                table_name VARCHAR PRIMARY KEY,
                schema_json VARCHAR,
                last_checked_at TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS source_freshness (
                source_name VARCHAR PRIMARY KEY,
                max_loaded_at TIMESTAMP,
                status VARCHAR,
                checked_at TIMESTAMP
            )
        """)

    def is_up_to_date(self, model_name: str, current_hash: str) -> bool:
        result = self.conn.execute(
            "SELECT hash FROM model_state WHERE model_name = ?",
            [model_name],
        ).fetchone()
        if result is None:
            return False
        return result[0] == current_hash

    def record_run(
        self, model_name: str, model_hash: str, row_count: int = 0
    ) -> None:
        with self._lock:
            self.conn.execute("""
                INSERT INTO model_state (model_name, hash, last_run_at, row_count)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (model_name) DO UPDATE SET
                    hash = EXCLUDED.hash,
                    last_run_at = EXCLUDED.last_run_at,
                    row_count = EXCLUDED.row_count
            """, [model_name, model_hash, datetime.now(), row_count])

    def record_schema(self, table_name: str, schema_json: str) -> None:
        with self._lock:
            self.conn.execute("""
                INSERT INTO schema_state (table_name, schema_json, last_checked_at)
                VALUES (?, ?, ?)
                ON CONFLICT (table_name) DO UPDATE SET
                    schema_json = EXCLUDED.schema_json,
                    last_checked_at = EXCLUDED.last_checked_at
            """, [table_name, schema_json, datetime.now()])

    def get_schema(self, table_name: str) -> dict | None:
        result = self.conn.execute(
            "SELECT schema_json FROM schema_state WHERE table_name = ?",
            [table_name],
        ).fetchone()
        if result:
            return {"table_name": table_name, "schema_json": result[0]}
        return None

    def get_state(self, model_name: str) -> dict | None:
        result = self.conn.execute(
            "SELECT * FROM model_state WHERE model_name = ?",
            [model_name],
        ).fetchone()
        if result:
            return {
                "model_name": result[0],
                "hash": result[1],
                "last_run_at": result[2].isoformat() if result[2] else None,
                "row_count": result[3],
            }
        return None

    def get_all_states(self) -> list[dict]:
        results = self.conn.execute("SELECT * FROM model_state").fetchall()
        return [
            {
                "model_name": r[0],
                "hash": r[1],
                "last_run_at": r[2].isoformat() if r[2] else None,
                "row_count": r[3],
            }
            for r in results
        ]

    def get_hash(self, model_name: str) -> str | None:
        result = self.conn.execute(
            "SELECT hash FROM model_state WHERE model_name = ?",
            [model_name],
        ).fetchone()
        return result[0] if result else None

    def record_freshness(self, source_name: str, max_loaded_at: datetime | None, status: str) -> None:
        with self._lock:
            self.conn.execute("""
                INSERT INTO source_freshness (source_name, max_loaded_at, status, checked_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (source_name) DO UPDATE SET
                    max_loaded_at = EXCLUDED.max_loaded_at,
                    status = EXCLUDED.status,
                    checked_at = EXCLUDED.checked_at
            """, [source_name, max_loaded_at, status, datetime.now()])

    def get_freshness(self, source_name: str) -> dict | None:
        result = self.conn.execute(
            "SELECT source_name, max_loaded_at, status, checked_at FROM source_freshness WHERE source_name = ?",
            [source_name],
        ).fetchone()
        if result:
            return {
                "source_name": result[0],
                "max_loaded_at": result[1].isoformat() if result[1] else None,
                "status": result[2],
                "checked_at": result[3].isoformat() if result[3] else None,
            }
        return None

    def get_all_freshness(self) -> list[dict]:
        results = self.conn.execute("SELECT source_name, max_loaded_at, status, checked_at FROM source_freshness").fetchall()
        return [
            {
                "source_name": r[0],
                "max_loaded_at": r[1].isoformat() if r[1] else None,
                "status": r[2],
                "checked_at": r[3].isoformat() if r[3] else None,
            }
            for r in results
        ]

    def reset(self, model_name: str | None = None) -> None:
        with self._lock:
            if model_name:
                self.conn.execute(
                    "DELETE FROM model_state WHERE model_name = ?", [model_name]
                )
            else:
                self.conn.execute("DELETE FROM model_state")
                self.conn.execute("DELETE FROM schema_state")

    def close(self):
        self.conn.execute("CHECKPOINT")
        self.conn.close()
        if self._use_encryption:
            if self._tmp_path and self._tmp_path.exists():
                raw = self._tmp_path.read_bytes()
                self.db_path.write_bytes(raw)
                encrypt_file(self.db_path)
                self._tmp_path.unlink(missing_ok=True)
            else:
                encrypt_file(self.db_path)
