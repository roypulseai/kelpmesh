"""Right to be Forgotten — purge PII across warehouse tables."""

import logging
import re
from datetime import datetime
from pathlib import Path

from kelpmesh.core.errors import sanitize_exception_message

_logger = logging.getLogger(__name__)

from kelpmesh.security.classifier import DataClassifier, SensitivityLevel
from kelpmesh.security.audit import AuditLog
from kelpmesh.adapters.base import WarehouseAdapter


def _resolve_identifier(identifier: str) -> str:
    """Normalise an identifier (email, user_id, etc.) for matching."""
    return identifier.strip().lower()


def _pii_columns(
    classifier: DataClassifier, tables: list[str]
) -> dict[str, list[str]]:
    """Return {table: [pii_column, ...]} for all pii-classified columns."""
    result: dict[str, list[str]] = {}
    for table in tables:
        # Use the classifier's built-in name rules to find PII columns
        pii_cols = classifier.columns_by_sensitivity(table, "pii")
        # Also include any table-specific PII rules
        table_rules = classifier.get_table_rules(table)
        for col, sens in table_rules.items():
            if sens == "pii" and col not in pii_cols:
                pii_cols.append(col)
        if pii_cols:
            result[table] = pii_cols
    return result


def build_erase_sql(
    table: str,
    pii_columns: list[str],
    identifier_column: str,
    identifier_value: str,
) -> str:
    """Generate UPDATE SQL to null out PII columns for a given identifier."""
    set_clauses = ", ".join(
        f'"{col}" = NULL' for col in pii_columns
    )
    return f"""UPDATE "{table}"
SET {set_clauses},
    _pii_erased_at = '{datetime.utcnow().isoformat()}'
WHERE LOWER("{identifier_column}") = '{_resolve_identifier(identifier_value)}'"""


def ensure_erasure_column(adapter: WarehouseAdapter, table: str):
    """Ensure _pii_erased_at metadata column exists on the table."""
    try:
        adapter.execute(f'ALTER TABLE "{table}" ADD COLUMN _pii_erased_at TIMESTAMP')
    except Exception as e:
        _logger.debug("Could not add erasure column to %s: %s", table, e)


def erase_pii(
    adapter: WarehouseAdapter,
    classifier: DataClassifier,
    audit_log: AuditLog,
    identifier_column: str,
    identifier_value: str,
    tables: list[str] | None = None,
    actor: str = "system",
    dry_run: bool = False,
) -> dict:
    """Erase PII for an identifier across all (or specified) tables.

    Returns {table: rows_affected, ...}.
    """
    if tables is None:
        tables = _list_warehouse_tables(adapter)

    pii_map = _pii_columns(classifier, tables)
    results: dict[str, int] = {}

    for table, pii_cols in pii_map.items():
        ensure_erasure_column(adapter, table)
        sql = build_erase_sql(table, pii_cols, identifier_column, identifier_value)

        if dry_run:
            audit_log.record(
                action="pii_erase.dry_run",
                actor=actor,
                resource=f"table:{table}",
                status="dry_run",
                detail=f"Would erase {len(pii_cols)} PII columns where {identifier_column}={identifier_value}",
            )
            results[table] = 0
            continue

        try:
            result = adapter.execute(sql)
            rows = len(result) if result else 0
            results[table] = rows
            audit_log.record(
                action="pii_erase",
                actor=actor,
                resource=f"table:{table}",
                status="success",
                detail=f"Erased {len(pii_cols)} PII columns, {rows} rows affected",
                after={"rows_erased": rows, "columns": pii_cols},
            )
        except Exception as e:
            results[table] = -1
            audit_log.record(
                action="pii_erase",
                actor=actor,
                resource=f"table:{table}",
                status="failed",
                detail=sanitize_exception_message(str(e)),
            )

    return results


def _list_warehouse_tables(adapter: WarehouseAdapter) -> list[str]:
    """List all tables in the warehouse."""
    try:
        rows = adapter.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_type = 'BASE TABLE'"
        )
        return [r["table_name"] for r in rows]
    except Exception as e:
        _logger.debug("Could not list warehouse tables: %s", e)
        return []

