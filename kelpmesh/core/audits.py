"""Grain and audit checks — run after a model materializes.

grain:  Verifies that the specified columns are unique together (no duplicate
        composite keys). Equivalent to SQLMesh's ``grain:`` declaration.

audits: Named SQL queries that must return zero rows.  If any row is returned
        the audit fails.  Equivalent to SQLMesh's ``audits:`` list in a MODEL block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kelpmesh.adapters.base import WarehouseAdapter
    from kelpmesh.core.model import BriqModel


@dataclass
class AuditResult:
    name: str
    passed: bool
    failures: int = 0
    message: str = ""


def check_grain(
    model: "BriqModel",
    table_name: str,
    adapter: "WarehouseAdapter",
) -> AuditResult:
    """Verify that *grain* columns are unique together in *table_name*."""
    if not model.grain:
        return AuditResult(name=f"{model.name}.grain", passed=True)

    cols = ", ".join(f'"{c}"' for c in model.grain)
    sql = f"""
        SELECT COUNT(*) AS failures
        FROM (
            SELECT {cols}, COUNT(*) AS cnt
            FROM {table_name}
            GROUP BY {cols}
            HAVING COUNT(*) > 1
        ) _dups
    """
    try:
        rows = adapter.execute(sql)
        failures = int(rows[0]["failures"]) if rows else 0
        return AuditResult(
            name=f"{model.name}.grain",
            passed=failures == 0,
            failures=failures,
            message=(
                "" if failures == 0
                else f"{failures} duplicate grain combination(s) on [{', '.join(model.grain)}]"
            ),
        )
    except Exception as exc:
        return AuditResult(
            name=f"{model.name}.grain",
            passed=False,
            failures=0,
            message=f"grain check error: {exc}",
        )


def run_audits(
    model: "BriqModel",
    table_name: str,
    adapter: "WarehouseAdapter",
    audits_dir: Path | None = None,
) -> list[AuditResult]:
    """Run named audit SQL files against *table_name*.

    Each audit file must return zero rows to pass.  Audit SQL may reference
    ``{table}`` which is substituted with the actual table name.

    Audit files are looked up in (in order):
      1. ``audits_dir`` argument
      2. ``<project>/tests/audits/`` relative to the model's file path
      3. ``<project>/audits/``
    """
    if not model.audits:
        return []

    # Build search paths
    search_paths: list[Path] = []
    if audits_dir:
        search_paths.append(Path(audits_dir))
    model_project = model.file_path.parent.parent
    for candidate in ("tests/audits", "audits"):
        p = model_project / candidate
        if p.exists():
            search_paths.append(p)

    results: list[AuditResult] = []

    for audit_name in model.audits:
        sql_file = None
        for sp in search_paths:
            candidate_file = sp / f"{audit_name}.sql"
            if candidate_file.exists():
                sql_file = candidate_file
                break

        if sql_file is None:
            results.append(AuditResult(
                name=f"{model.name}.audit:{audit_name}",
                passed=False,
                message=f"Audit file '{audit_name}.sql' not found in search paths: "
                        + ", ".join(str(s) for s in search_paths),
            ))
            continue

        audit_sql = sql_file.read_text(encoding="utf-8")
        audit_sql = audit_sql.replace("{table}", table_name)

        try:
            rows = adapter.execute(audit_sql)
            failures = len(rows)
            results.append(AuditResult(
                name=f"{model.name}.audit:{audit_name}",
                passed=failures == 0,
                failures=failures,
                message="" if failures == 0 else f"{failures} failing row(s) returned",
            ))
        except Exception as exc:
            results.append(AuditResult(
                name=f"{model.name}.audit:{audit_name}",
                passed=False,
                message=f"Audit execution error: {exc}",
            ))

    return results


def run_inline_audits(
    model: "BriqModel",
    table_name: str,
    adapter: "WarehouseAdapter",
    project_path: Path | None = None,
) -> list[AuditResult]:
    """Convenience: run grain check + named audits, returning combined results."""
    results: list[AuditResult] = []
    if model.grain:
        results.append(check_grain(model, table_name, adapter))
    audits_dir = (project_path / "audits") if project_path else None
    results.extend(run_audits(model, table_name, adapter, audits_dir=audits_dir))
    return results
