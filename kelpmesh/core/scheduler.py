"""Built-in cron scheduler — run kelpmesh jobs on a schedule without Airflow.

Supports two schedule formats:
  - Cron syntax:       "0 6 * * *"  (daily at 06:00 UTC)
  - Interval syntax:   "every 1h", "every 30m", "every 1d"

Usage in kelpmesh.yml:

    schedules:
      - name: daily_refresh
        cron: "0 6 * * *"
        command: run
        args: ["--tag", "daily"]

      - name: hourly_metrics
        interval: "every 1h"
        command: run
        args: ["--select", "metrics"]

      - name: weekly_snapshot
        cron: "0 0 * * 1"
        command: snapshot

Then start the daemon:
    kelpmesh schedule start [--daemon]

Stop it:
    kelpmesh schedule stop

Show next run times:
    kelpmesh schedule list
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


# ─────────────────────────────────────────────────────────────────────────── #
# Schedule representation                                                      #
# ─────────────────────────────────────────────────────────────────────────── #

_INTERVAL_RE = re.compile(
    r"every\s+(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>s(?:ec(?:ond)?s?)?|m(?:in(?:ute)?s?)?|h(?:our)?s?|d(?:ay)?s?)",
    re.IGNORECASE,
)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


@dataclass
class Schedule:
    name: str
    command: str
    args: list[str]
    # exactly one of these is set:
    cron: str | None = None
    interval_seconds: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Schedule":
        name = d.get("name", "unnamed")
        command = d.get("command", "run")
        args = [str(a) for a in d.get("args", [])]

        cron = d.get("cron")
        interval_str = d.get("interval")

        interval_seconds = None
        if interval_str:
            m = _INTERVAL_RE.match(str(interval_str).strip())
            if m:
                n = float(m.group("n"))
                unit = m.group("unit")[0].lower()
                interval_seconds = n * _UNIT_SECONDS[unit]
            else:
                raise ValueError(
                    f"Unrecognised interval format: {interval_str!r}. "
                    f"Use e.g. 'every 1h', 'every 30m', 'every 1d'."
                )

        if cron is None and interval_seconds is None:
            raise ValueError(f"Schedule {name!r} needs either 'cron' or 'interval'.")

        return cls(name=name, command=command, args=args,
                   cron=cron, interval_seconds=interval_seconds)

    def next_run_after(self, after: datetime) -> datetime:
        """Compute the next fire time after *after* (UTC)."""
        if self.interval_seconds is not None:
            return datetime.fromtimestamp(
                after.timestamp() + self.interval_seconds, tz=timezone.utc
            )
        # cron
        return _next_cron(self.cron, after)  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────────────── #
# Minimal cron parser — no external dependency                                 #
# ─────────────────────────────────────────────────────────────────────────── #

def _parse_field(field: str, lo: int, hi: int) -> list[int]:
    """Parse a single cron field (minute, hour, dom, month, dow)."""
    values: set[int] = set()
    for part in field.split(","):
        if part == "*":
            values.update(range(lo, hi + 1))
        elif "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if base == "*":
                start = lo
            elif "-" in base:
                a, b = base.split("-")
                start = int(a)
            else:
                start = int(base)
            values.update(range(start, hi + 1, step))
        elif "-" in part:
            a, b = part.split("-")
            values.update(range(int(a), int(b) + 1))
        else:
            values.add(int(part))
    return sorted(values)


def _next_cron(cron: str, after: datetime) -> datetime:
    """Return the next UTC datetime matching *cron* after *after*."""
    parts = cron.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Cron expression must have 5 fields: {cron!r}")

    minutes  = _parse_field(parts[0], 0, 59)
    hours    = _parse_field(parts[1], 0, 23)
    days     = _parse_field(parts[2], 1, 31)
    months   = _parse_field(parts[3], 1, 12)
    weekdays = _parse_field(parts[4], 0, 6)  # 0=Sunday

    def _candidates(dt: datetime) -> Iterator[datetime]:
        for year in range(dt.year, dt.year + 5):
            for month in months:
                import calendar
                max_day = calendar.monthrange(year, month)[1]
                for day in days:
                    if day > max_day:
                        continue
                    try:
                        d = datetime(year, month, day, tzinfo=timezone.utc)
                    except ValueError:
                        continue
                    # dow: Python weekday() 0=Mon; cron 0=Sun
                    py_dow = (d.weekday() + 1) % 7  # convert to Sun=0
                    if py_dow not in weekdays:
                        continue
                    for hour in hours:
                        for minute in minutes:
                            candidate = datetime(
                                year, month, day, hour, minute, 0,
                                tzinfo=timezone.utc
                            )
                            if candidate > after:
                                yield candidate

    return next(_candidates(after))


# ─────────────────────────────────────────────────────────────────────────── #
# Scheduler daemon                                                             #
# ─────────────────────────────────────────────────────────────────────────── #

class KelpMeshScheduler:
    """Thread-per-schedule daemon that fires kelpmesh CLI commands."""

    def __init__(self, schedules: list[Schedule], project_path: Path,
                 log_path: Path | None = None) -> None:
        self._schedules = schedules
        self._project_path = project_path
        self._log_path = log_path or (project_path / "logs" / "scheduler.log")
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()

    def start(self) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        for sched in self._schedules:
            t = threading.Thread(
                target=self._run_schedule,
                args=(sched,),
                name=f"km-sched-{sched.name}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)
            self._log(f"[scheduler] started: {sched.name}")

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)
        self._threads.clear()
        self._log("[scheduler] stopped")

    def wait(self) -> None:
        try:
            while not self._stop.is_set():
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.stop()

    def _run_schedule(self, sched: Schedule) -> None:
        now = datetime.now(tz=timezone.utc)
        next_run = sched.next_run_after(now)
        while not self._stop.is_set():
            now = datetime.now(tz=timezone.utc)
            if now >= next_run:
                self._fire(sched)
                next_run = sched.next_run_after(now)
            sleep_secs = min(30, max(1, (next_run - now).total_seconds()))
            self._stop.wait(timeout=sleep_secs)

    def _fire(self, sched: Schedule) -> None:
        cmd = [sys.executable, "-m", "kelpmesh", sched.command] + sched.args
        self._log(f"[{sched.name}] firing: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self._project_path),
                capture_output=True,
                text=True,
                timeout=7200,
            )
            status = "OK" if result.returncode == 0 else f"FAIL(rc={result.returncode})"
            self._log(f"[{sched.name}] {status}")
            if result.returncode != 0 and result.stderr:
                self._log(f"[{sched.name}] stderr: {result.stderr[:500]}")
        except subprocess.TimeoutExpired:
            self._log(f"[{sched.name}] TIMEOUT after 2 hours — killed")
        except Exception as exc:
            self._log(f"[{sched.name}] ERROR: {exc}")

    def _log(self, msg: str) -> None:
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"{ts}  {msg}"
        try:
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass
        print(line, flush=True)

    def next_runs(self) -> list[dict]:
        """Return a list of {name, next_run, cron/interval} for display."""
        now = datetime.now(tz=timezone.utc)
        results = []
        for sched in self._schedules:
            nr = sched.next_run_after(now)
            results.append({
                "name": sched.name,
                "next_run": nr.strftime("%Y-%m-%d %H:%M UTC"),
                "schedule": sched.cron or f"every {sched.interval_seconds}s",
                "command": f"kelpmesh {sched.command} {' '.join(sched.args)}".strip(),
            })
        return sorted(results, key=lambda r: r["next_run"])


# ─────────────────────────────────────────────────────────────────────────── #
# Project config loader                                                        #
# ─────────────────────────────────────────────────────────────────────────── #

def load_schedules_from_project(project_path: Path) -> list[Schedule]:
    """Read schedules: from kelpmesh.yml and return Schedule objects."""
    config_file = project_path / "kelpmesh.yml"
    if not config_file.exists():
        return []
    try:
        import yaml
        data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw = (data or {}).get("schedules", [])
    schedules = []
    for entry in raw:
        try:
            schedules.append(Schedule.from_dict(entry))
        except ValueError as exc:
            print(f"[scheduler] skipping invalid schedule entry: {exc}", flush=True)
    return schedules


Scheduler = KelpMeshScheduler
