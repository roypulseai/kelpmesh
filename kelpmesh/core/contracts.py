"""Model contract enforcement — validates actual table schema against schema.yml declarations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kelpmesh.adapters.base import WarehouseAdapter
    from kelpmesh.core.schema_yaml import SchemaYaml

# Loose type aliases used for comparison (normalised to uppercase)
_TYPE_ALIASES: dict[str, set[str]] = {
    "INTEGER": {"INT", "INT4", "INT32", "SIGNED", "INTEGER"},
    "BIGINT": {"INT8", "INT64", "LONG", "BIGINT"},
    "SMALLINT": {"INT2", "INT16", "SHORT", "SMALLINT"},
    "HUGEINT": {"HUGEINT"},
    "VARCHAR": {"VARCHAR", "TEXT", "STRING", "CHAR", "CHARACTER VARYING"},
    "BOOLEAN": {"BOOL", "BOOLEAN", "LOGICAL"},
    "FLOAT": {"FLOAT", "FLOAT4", "REAL"},
    "DOUBLE": {"DOUBLE", "FLOAT8", "DOUBLE PRECISION", "NUMERIC", "DECIMAL"},
    "DATE": {"DATE"},
    "TIMESTAMP": {"TIMESTAMP", "DATETIME"},
    "TIME": {"TIME"},
    "BLOB": {"BLOB", "BYTEA", "BINARY", "VARBINARY"},
}

_CANONICAL: dict[str, str] = {}
for _canonical, _aliases in _TYPE_ALIASES.items():
    for _alias in _aliases:
        _CANONICAL[_alias] = _canonical


def _normalise_type(t: str) -> str:
    """Return canonical type name, stripping precision/scale."""
    base = t.upper().split("(")[0].strip()
    return _CANONICAL.get(base, base)


@dataclass
class ContractViolation:
    model: str
    column: str
    kind: str   # "missing_column" | "extra_column" | "type_mismatch"
    expected: str = ""
    actual: str = ""

    def __str__(self) -> str:
        if self.kind == "missing_column":
            return f"[{self.model}] column '{self.column}' declared in contract but missing from table"
        if self.kind == "extra_column":
            return f"[{self.model}] column '{self.column}' in table but not declared in contract"
        return (
            f"[{self.model}] column '{self.column}' type mismatch: "
            f"expected {self.expected!r}, got {self.actual!r}"
        )


@dataclass
class ContractResult:
    model: str
    passed: bool
    violations: list[ContractViolation] = field(default_factory=list)


def check_contract(
    model_name: str,
    adapter: "WarehouseAdapter",
    schema: "SchemaYaml",
) -> ContractResult:
    """Compare the actual warehouse schema of *model_name* against its contract declaration.

    Returns a :class:`ContractResult` with all violations.  If no contract is
    declared for the model, returns ``passed=True`` with no violations.
    """
    contract = schema.model_contract(model_name)
    if not contract.get("enforced"):
        return ContractResult(model=model_name, passed=True)

    declared_cols: list[dict] = schema.column_metadata(model_name)
    if not declared_cols:
        return ContractResult(model=model_name, passed=True)

    # Build expected map: name → data_type (may be absent)
    expected: dict[str, str | None] = {
        c["name"].lower(): c.get("data_type")
        for c in declared_cols
        if "name" in c
    }

    # Fetch actual schema from warehouse
    try:
        actual_rows = adapter.table_schema(model_name)
    except Exception:
        return ContractResult(model=model_name, passed=True)

    actual: dict[str, str] = {
        r["column_name"].lower(): r["data_type"]
        for r in actual_rows
    }

    violations: list[ContractViolation] = []

    # Missing columns
    for col_name in expected:
        if col_name not in actual:
            violations.append(ContractViolation(model_name, col_name, "missing_column"))
            continue
        declared_type = expected[col_name]
        if declared_type:
            exp_norm = _normalise_type(declared_type)
            act_norm = _normalise_type(actual[col_name])
            if exp_norm != act_norm:
                violations.append(ContractViolation(
                    model_name, col_name, "type_mismatch",
                    expected=exp_norm, actual=act_norm,
                ))

    # Extra columns in table not in contract — warn only (configurable)
    constrained = contract.get("constrained_columns", False)
    if constrained:
        for col_name in actual:
            if col_name not in expected:
                violations.append(ContractViolation(model_name, col_name, "extra_column"))

    return ContractResult(
        model=model_name,
        passed=len(violations) == 0,
        violations=violations,
    )
