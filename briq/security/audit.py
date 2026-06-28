"""Audit logging — every CLI/API action with before/after state."""

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path


class AuditLog:
    """Structured audit trail backed by a JSONL file in target/."""

    def __init__(self, project_path: Path):
        self.log_path = project_path / "target" / "audit.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()
        self._lock = threading.Lock()

    def record(
        self,
        action: str,
        actor: str | None,
        resource: str,
        status: str = "success",
        before: dict | None = None,
        after: dict | None = None,
        detail: str | None = None,
    ) -> dict:
        entry = {
            "id": str(uuid.uuid4())[:12],
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "action": action,
            "actor": actor or "system",
            "resource": resource,
            "status": status,
            "before": before,
            "after": after,
            "detail": detail,
        }
        with self._lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        return entry

    def query(
        self,
        limit: int = 100,
        actor: str | None = None,
        action: str | None = None,
        resource: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        if not self.log_path.exists():
            return []
        results = []
        with self._lock:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if actor and entry.get("actor") != actor:
                        continue
                    if action and entry.get("action") != action:
                        continue
                    if resource and resource not in entry.get("resource", ""):
                        continue
                    if status and entry.get("status") != status:
                        continue
                    results.append(entry)
        return results[-limit:]

    def count_by_action(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        if not self.log_path.exists():
            return counts
        with self._lock:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    a = entry.get("action", "unknown")
                    counts[a] = counts.get(a, 0) + 1
        return counts

    def clear(self) -> None:
        if self.log_path.exists():
            self.log_path.unlink()
