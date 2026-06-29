"""Dynamic Column Masking — inject SQL-level masking based on sensitivity + role.

Masking strategies injected at query time. Never touches the base table.
"""

from kelpmesh.security.classifier import DataClassifier, SensitivityLevel

# Role hierarchy (higher index = more privileged)
ROLE_HIERARCHY = ["viewer", "editor", "admin"]

# Which sensitivity levels each role can see unmasked
ROLE_ACCESS: dict[str, set[SensitivityLevel]] = {
    "viewer": {"internal"},
    "editor": {"internal", "restricted"},
    "admin": {"internal", "restricted", "sensitive", "pii"},
}

MASK_STRATEGIES = {
    "pii": {
        "email": r"regexp_replace({col}, '(.).*@(.*)', '\1***@\2')",
        "phone": r"regexp_replace({col}, '(\d{3})\d{4}(\d{2})', '\1****\2')",
        "default": r"concat(left({col}::varchar, 2), '****')",
    },
    "sensitive": {
        "credit_card": r"concat('****-****-****-', right({col}::varchar, 4))",
        "default": "'[REDACTED - SENSITIVE]'",
    },
    "restricted": {
        "default": "'[REDACTED - RESTRICTED]'",
    },
    "internal": {},
}


def column_mask_sql(
    column: str,
    sensitivity: SensitivityLevel,
    strategy_overrides: dict | None = None,
) -> str | None:
    """Return the masking SQL expression for a column, or None if unmasked."""
    strategies = strategy_overrides or MASK_STRATEGIES
    level_strategies = strategies.get(sensitivity, {})
    if not level_strategies:
        return None
    col_lower = column.lower()
    if col_lower in level_strategies:
        template = level_strategies[col_lower]
    else:
        template = level_strategies.get("default")
    if template is None:
        return None
    return template.replace("{col}", f'"{column}"')


def get_masked_select(
    table: str,
    columns: list[str],
    user_role: str,
    classifier: DataClassifier,
    strategy_overrides: dict | None = None,
) -> str:
    """Build a SELECT clause with masking applied based on user role."""
    masked_cols = []
    for col in columns:
        sens = classifier.classify(table, col)
        if sens in ROLE_ACCESS.get(user_role, {"internal"}):
            masked_cols.append(f'"{col}"')
        else:
            mask_expr = column_mask_sql(col, sens, strategy_overrides)
            if mask_expr:
                masked_cols.append(f"{mask_expr} AS \"{col}\"")
            else:
                masked_cols.append(f'"{col}"')
    return ", ".join(masked_cols)


def can_access_column(
    sensitivity: SensitivityLevel, user_role: str
) -> bool:
    return sensitivity in ROLE_ACCESS.get(user_role, {"internal"})
