"""kelpmesh lint — SQL linter that checks model files for common issues.

Runs a suite of rule-based checks against every .sql file in the models/
directory and reports violations with filename, line number, rule ID, message,
and severity.  Exit code is 1 when any error-level findings exist.

Rules implemented
-----------------
L001  SELECT *          Avoid SELECT * — list columns explicitly
L002  Missing ref()     Raw table name used instead of ref('model')
L003  Hardcoded date    Date literal in WHERE without a variable
L004  Mixed CTE style   CTEs and subqueries mixed in the same model
L005  No PK test        Model has no unique/not_null test for a key column
L006  Trailing space    Trailing whitespace or inconsistent indentation
L007  Lowercase SQL kw  SQL keywords should be uppercase
L008  Ambiguous column  Column reference without table alias in a JOIN
L009  Unused CTE        CTE defined but never referenced in the query body
L010  No description    Model has no description entry in schema.yml
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

SEVERITY_ERROR = "error"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"

_SEVERITY_STYLE = {
    SEVERITY_ERROR: "red",
    SEVERITY_WARN: "yellow",
    SEVERITY_INFO: "dim",
}


@dataclass
class LintViolation:
    filename: str
    line: int
    rule_id: str
    message: str
    severity: str
    fixable: bool = False
    fix_hint: str = ""


# ---------------------------------------------------------------------------
# Individual rule implementations
# ---------------------------------------------------------------------------

_SQL_KEYWORDS = [
    "SELECT", "FROM", "WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER",
    "FULL", "CROSS", "ON", "GROUP BY", "ORDER BY", "HAVING", "UNION",
    "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "WITH",
    "CASE", "WHEN", "THEN", "ELSE", "END", "AS", "AND", "OR", "NOT",
    "IN", "BETWEEN", "LIKE", "IS", "NULL", "DISTINCT", "LIMIT", "OFFSET",
    "PARTITION", "OVER", "ROWS", "RANGE",
]

# Regex for a bare table reference: word.word or just word used after FROM/JOIN
# that is NOT wrapped in ref(...) or source(...).
_RAW_TABLE_RE = re.compile(
    r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)\s*(?:AS\s+\w+)?\b",
    re.IGNORECASE,
)
_REF_SOURCE_RE = re.compile(r"(?:ref|source)\s*\(", re.IGNORECASE)
_DATE_LITERAL_RE = re.compile(r"['\"](\d{4}-\d{2}-\d{2})['\"]")
_CTE_DEF_RE = re.compile(r"^\s*(\w+)\s+AS\s*\(", re.IGNORECASE | re.MULTILINE)
_WITH_RE = re.compile(r"\bWITH\b", re.IGNORECASE)
_SUBQUERY_RE = re.compile(r"\(\s*SELECT\b", re.IGNORECASE)
_TRAILING_SPACE_RE = re.compile(r"[ \t]+$", re.MULTILINE)
_JOIN_COL_RE = re.compile(r"\bON\b.*?\b(\w+)\s*=\s*(\w+)\b", re.IGNORECASE | re.DOTALL)


def _check_L001(lines: list[str], filename: str) -> list[LintViolation]:
    """L001: SELECT * in model."""
    violations = []
    for i, line in enumerate(lines, 1):
        if re.search(r"\bSELECT\s+\*", line, re.IGNORECASE):
            violations.append(LintViolation(
                filename=filename,
                line=i,
                rule_id="L001",
                message="Avoid SELECT * — list columns explicitly",
                severity=SEVERITY_WARN,
            ))
    return violations


def _check_L002(lines: list[str], filename: str, sql: str) -> list[LintViolation]:
    """L002: Raw table reference instead of ref('model')."""
    violations = []
    # Skip files that already use ref() exclusively — only flag if there's a
    # FROM/JOIN that doesn't use ref() on the same logical line cluster.
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not re.search(r"\b(?:FROM|JOIN)\b", stripped, re.IGNORECASE):
            continue
        # If this FROM/JOIN line contains ref( or source( — it's fine.
        if _REF_SOURCE_RE.search(stripped):
            continue
        # If it's a subquery opening paren — skip.
        if re.search(r"\bFROM\s*\(", stripped, re.IGNORECASE):
            continue
        # Otherwise flag it.
        m = _RAW_TABLE_RE.search(stripped)
        if m:
            table_ref = m.group(1)
            # Ignore common non-model tokens like DUAL, UNNEST, etc.
            if table_ref.lower() in {"dual", "unnest", "lateral", "values"}:
                continue
            violations.append(LintViolation(
                filename=filename,
                line=i,
                rule_id="L002",
                message=f"Raw table reference '{table_ref}' — use ref('{table_ref.split('.')[-1]}') instead",
                severity=SEVERITY_WARN,
            ))
    return violations


def _check_L003(lines: list[str], filename: str) -> list[LintViolation]:
    """L003: Hardcoded date literal in WHERE clause."""
    violations = []
    in_where = False
    for i, line in enumerate(lines, 1):
        if re.search(r"\bWHERE\b", line, re.IGNORECASE):
            in_where = True
        if in_where and _DATE_LITERAL_RE.search(line):
            # Allow if it's inside a var() call or a jinja expression.
            if re.search(r"\{\{.*?\}\}", line):
                continue
            violations.append(LintViolation(
                filename=filename,
                line=i,
                rule_id="L003",
                message="Hardcoded date literal in WHERE — use a variable or parameter instead",
                severity=SEVERITY_WARN,
            ))
        if re.search(r"\b(?:GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|SELECT)\b", line, re.IGNORECASE):
            in_where = False
    return violations


def _check_L004(lines: list[str], filename: str, sql: str) -> list[LintViolation]:
    """L004: Mixed CTE style — CTEs and subqueries used together."""
    violations = []
    has_cte = bool(_WITH_RE.search(sql) and _CTE_DEF_RE.search(sql))
    has_subquery = bool(_SUBQUERY_RE.search(sql))
    if has_cte and has_subquery:
        # Find first subquery line to pin the violation.
        for i, line in enumerate(lines, 1):
            if _SUBQUERY_RE.search(line):
                violations.append(LintViolation(
                    filename=filename,
                    line=i,
                    rule_id="L004",
                    message="Mixed CTE/subquery style — prefer CTEs for readability",
                    severity=SEVERITY_INFO,
                ))
                break
    return violations


def _check_L005(filename: str, project_path: Path, model_stem: str) -> list[LintViolation]:
    """L005: No unique/not_null test for a key column in schema.yml."""
    violations = []
    schema_candidates = [
        project_path / "models" / "schema.yml",
        project_path / "models" / "_schema.yml",
        project_path / "models" / "schema.yaml",
    ]
    try:
        import yaml
    except ImportError:
        return violations  # can't check without yaml

    for schema_path in schema_candidates:
        if not schema_path.exists():
            continue
        try:
            with open(schema_path) as f:
                schema = yaml.safe_load(f) or {}
        except Exception:
            continue

        models_list = schema.get("models", [])
        for m in models_list:
            if m.get("name") != model_stem:
                continue
            # Model found — check if any column has unique+not_null tests.
            columns = m.get("columns", [])
            has_pk_test = False
            for col in columns:
                tests = col.get("tests", [])
                test_names = {
                    (t if isinstance(t, str) else list(t.keys())[0])
                    for t in tests
                }
                if "unique" in test_names and "not_null" in test_names:
                    has_pk_test = True
                    break
            if not has_pk_test and columns:
                violations.append(LintViolation(
                    filename=filename,
                    line=1,
                    rule_id="L005",
                    message=f"Model '{model_stem}' has no column with both unique + not_null tests (primary key)",
                    severity=SEVERITY_WARN,
                ))
            return violations  # found the model entry — stop searching files

    return violations


def _check_L006(lines: list[str], filename: str) -> list[LintViolation]:
    """L006: Trailing whitespace or inconsistent indentation."""
    violations = []
    indent_styles: set[str] = set()
    for i, line in enumerate(lines, 1):
        if _TRAILING_SPACE_RE.search(line):
            violations.append(LintViolation(
                filename=filename,
                line=i,
                rule_id="L006",
                message="Trailing whitespace",
                severity=SEVERITY_INFO,
                fixable=True,
                fix_hint="Strip trailing whitespace from this line",
            ))
        stripped = line.lstrip()
        if stripped and line != stripped:
            leading = line[: len(line) - len(stripped)]
            if "\t" in leading:
                indent_styles.add("tab")
            else:
                indent_styles.add("space")

    if len(indent_styles) > 1:
        violations.append(LintViolation(
            filename=filename,
            line=1,
            rule_id="L006",
            message="Inconsistent indentation — file mixes tabs and spaces",
            severity=SEVERITY_INFO,
        ))
    return violations


def _check_L007(lines: list[str], filename: str) -> list[LintViolation]:
    """L007: SQL keywords not uppercase."""
    violations = []
    # Simple heuristic: check the most common keywords outside Jinja blocks.
    for i, line in enumerate(lines, 1):
        # Strip Jinja template parts before checking.
        clean = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", line)
        for kw in ("select", "from", "where", "join", "group by", "order by", "having"):
            pattern = r"\b" + kw.replace(" ", r"\s+") + r"\b"
            if re.search(pattern, clean, re.IGNORECASE) and re.search(pattern, clean):
                # The lower-case version matched but so did the case-insensitive one,
                # which means we found the keyword in lowercase.
                upper_kw = kw.upper()
                violations.append(LintViolation(
                    filename=filename,
                    line=i,
                    rule_id="L007",
                    message=f"SQL keyword should be uppercase: '{kw}' → '{upper_kw}'",
                    severity=SEVERITY_INFO,
                    fixable=True,
                    fix_hint=f"Replace '{kw}' with '{upper_kw}'",
                ))
                break  # one violation per line is enough
    return violations


def _check_L008(lines: list[str], filename: str, sql: str) -> list[LintViolation]:
    """L008: Ambiguous column reference in JOIN (no table alias prefix)."""
    violations = []
    # Only flag when there's at least one JOIN.
    if not re.search(r"\bJOIN\b", sql, re.IGNORECASE):
        return violations

    for i, line in enumerate(lines, 1):
        # Look for ON a.col = b.col patterns — if one side has no dot, flag it.
        m = re.search(
            r"\bON\b\s+(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)\b"
            r"|\bON\b\s+(\w+)\s*=\s*(\w+)\b",
            line,
            re.IGNORECASE,
        )
        if m:
            groups = m.groups()
            # If groups 4 and 5 matched (the simple `col = col` form without dots)
            if groups[4] is not None:
                violations.append(LintViolation(
                    filename=filename,
                    line=i,
                    rule_id="L008",
                    message="Ambiguous column reference in JOIN — qualify with table alias (e.g. t.col)",
                    severity=SEVERITY_WARN,
                ))
    return violations


def _check_L009(lines: list[str], filename: str, sql: str) -> list[LintViolation]:
    """L009: Unused CTE — defined but never referenced."""
    violations = []
    if not _WITH_RE.search(sql):
        return violations

    cte_names = [m.group(1) for m in _CTE_DEF_RE.finditer(sql)]
    if not cte_names:
        return violations

    # Body is everything after the last CTE closing paren — rough approximation.
    # A CTE is "used" if its name appears in the SQL outside its own definition block.
    for cte_name in cte_names:
        # Count occurrences of the CTE name across the whole SQL.
        occurrences = len(re.findall(r"\b" + re.escape(cte_name) + r"\b", sql, re.IGNORECASE))
        # One occurrence = the definition itself; need at least 2 to be "used".
        if occurrences < 2:
            # Find definition line.
            for i, line in enumerate(lines, 1):
                if re.search(
                    r"\b" + re.escape(cte_name) + r"\b\s+AS\s*\(",
                    line,
                    re.IGNORECASE,
                ):
                    violations.append(LintViolation(
                        filename=filename,
                        line=i,
                        rule_id="L009",
                        message=f"CTE '{cte_name}' is defined but never referenced",
                        severity=SEVERITY_WARN,
                    ))
                    break
    return violations


def _check_L010(filename: str, project_path: Path, model_stem: str) -> list[LintViolation]:
    """L010: Model has no description in schema.yml."""
    violations = []
    schema_candidates = [
        project_path / "models" / "schema.yml",
        project_path / "models" / "_schema.yml",
        project_path / "models" / "schema.yaml",
    ]
    try:
        import yaml
    except ImportError:
        return violations

    for schema_path in schema_candidates:
        if not schema_path.exists():
            continue
        try:
            with open(schema_path) as f:
                schema = yaml.safe_load(f) or {}
        except Exception:
            continue

        models_list = schema.get("models", [])
        found = False
        for m in models_list:
            if m.get("name") == model_stem:
                found = True
                if not m.get("description", "").strip():
                    violations.append(LintViolation(
                        filename=filename,
                        line=1,
                        rule_id="L010",
                        message=f"Model '{model_stem}' has no description in schema.yml",
                        severity=SEVERITY_INFO,
                    ))
                return violations  # found the entry
        if found:
            return violations

    # Model not in schema.yml at all.
    violations.append(LintViolation(
        filename=filename,
        line=1,
        rule_id="L010",
        message=f"Model '{model_stem}' is not documented in schema.yml",
        severity=SEVERITY_INFO,
    ))
    return violations


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

_ALL_RULES = ["L001", "L002", "L003", "L004", "L005", "L006", "L007", "L008", "L009", "L010"]


def _run_rules(
    sql_file: Path,
    project_path: Path,
    active_rules: set[str],
) -> list[LintViolation]:
    sql = sql_file.read_text(encoding="utf-8")
    lines = sql.splitlines()
    filename = str(sql_file.relative_to(project_path))
    model_stem = sql_file.stem
    violations: list[LintViolation] = []

    if "L001" in active_rules:
        violations += _check_L001(lines, filename)
    if "L002" in active_rules:
        violations += _check_L002(lines, filename, sql)
    if "L003" in active_rules:
        violations += _check_L003(lines, filename)
    if "L004" in active_rules:
        violations += _check_L004(lines, filename, sql)
    if "L005" in active_rules:
        violations += _check_L005(filename, project_path, model_stem)
    if "L006" in active_rules:
        violations += _check_L006(lines, filename)
    if "L007" in active_rules:
        violations += _check_L007(lines, filename)
    if "L008" in active_rules:
        violations += _check_L008(lines, filename, sql)
    if "L009" in active_rules:
        violations += _check_L009(lines, filename, sql)
    if "L010" in active_rules:
        violations += _check_L010(filename, project_path, model_stem)

    return violations


# ---------------------------------------------------------------------------
# Auto-fix helpers
# ---------------------------------------------------------------------------

def _apply_fixes(sql_file: Path, violations: list[LintViolation]) -> int:
    """Apply fixable violations to the file.  Returns count of fixes applied."""
    lines = sql_file.read_text(encoding="utf-8").splitlines(keepends=True)
    fixed = 0

    # L006: trailing whitespace (line-indexed fixes)
    trailing_lines = {v.line for v in violations if v.rule_id == "L006" and "Trailing" in v.message}
    for i in trailing_lines:
        idx = i - 1
        if 0 <= idx < len(lines):
            stripped = lines[idx].rstrip() + "\n"
            if stripped != lines[idx]:
                lines[idx] = stripped
                fixed += 1

    if fixed:
        sql_file.write_text("".join(lines), encoding="utf-8")
    return fixed


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

def lint_cmd(
    models: list[str] = typer.Argument(None, help="Model names to lint (default: all)"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
    select: list[str] = typer.Option(None, "--select", "-s", help="Model name selection filter"),
    rules: list[str] = typer.Option(None, "--rule", "-r", help="Specific rule IDs to run (default: all)"),
    ignore: list[str] = typer.Option(None, "--ignore", help="Rule IDs to skip"),
    format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text (default) or json.",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Auto-fix fixable issues (currently: L006 trailing whitespace).",
    ),
):
    """Lint SQL model files for common issues.

    Checks all .sql files in the models/ directory against a set of rules
    and reports violations.  Exit code is 1 if any error-level violations are found.

    Rules:
        L001  Avoid SELECT *
        L002  Missing ref() — raw table reference
        L003  Hardcoded date literal in WHERE
        L004  Mixed CTE/subquery style
        L005  No primary key test (unique + not_null)
        L006  Trailing whitespace / mixed indentation
        L007  SQL keywords not uppercase
        L008  Ambiguous column reference in JOIN
        L009  Unused CTE
        L010  Model missing description in schema.yml

    Examples:
        kelpmesh lint                          # lint all models, all rules
        kelpmesh lint --rule L001 --rule L007  # run only selected rules
        kelpmesh lint --ignore L010            # skip documentation check
        kelpmesh lint --format json            # machine-readable output
        kelpmesh lint --fix                    # auto-fix fixable issues
    """
    project_path = project_dir.resolve()
    models_dir = project_path / "models"

    if not models_dir.exists():
        console.print(f"[red]Models directory not found: {models_dir}[/red]")
        raise typer.Exit(1)

    # Determine active rule set.
    requested = set(r.upper() for r in rules) if rules else set(_ALL_RULES)
    ignored = set(r.upper() for r in ignore) if ignore else set()
    active_rules = requested - ignored

    # Collect files.
    all_sql = sorted(models_dir.rglob("*.sql"))
    combined_filter = list(models or []) + list(select or [])
    if combined_filter:
        all_sql = [f for f in all_sql if f.stem in combined_filter or any(n in str(f) for n in combined_filter)]

    if not all_sql:
        console.print("[yellow]No SQL files found.[/yellow]")
        raise typer.Exit(0)

    all_violations: list[LintViolation] = []
    fixes_applied = 0

    for sql_file in all_sql:
        try:
            viols = _run_rules(sql_file, project_path, active_rules)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Error reading {sql_file.name}: {exc}[/red]")
            continue

        if fix and viols:
            fixes_applied += _apply_fixes(sql_file, viols)

        all_violations += viols

    # Output
    if format == "json":
        output = [
            {
                "filename": v.filename,
                "line": v.line,
                "rule_id": v.rule_id,
                "message": v.message,
                "severity": v.severity,
                "fixable": v.fixable,
            }
            for v in all_violations
        ]
        console.print_json(json.dumps(output, indent=2))
    else:
        console.print()
        console.print(f"[bold]kelpmesh lint[/bold]  [dim]{project_path.name}[/dim]")
        console.print()

        if all_violations:
            table = Table(show_header=True, header_style="bold", expand=False)
            table.add_column("File", style="dim", no_wrap=True)
            table.add_column("Line", justify="right", style="dim", min_width=4)
            table.add_column("Rule", min_width=5)
            table.add_column("Severity", min_width=7)
            table.add_column("Message")

            for v in sorted(all_violations, key=lambda x: (x.filename, x.line, x.rule_id)):
                sev_style = _SEVERITY_STYLE.get(v.severity, "")
                table.add_row(
                    v.filename,
                    str(v.line),
                    f"[bold]{v.rule_id}[/bold]",
                    Text(v.severity, style=sev_style),
                    v.message,
                )

            console.print(table)
            console.print()

        # Summary counts by severity
        errors = sum(1 for v in all_violations if v.severity == SEVERITY_ERROR)
        warnings = sum(1 for v in all_violations if v.severity == SEVERITY_WARN)
        infos = sum(1 for v in all_violations if v.severity == SEVERITY_INFO)
        total = len(all_violations)

        if total == 0:
            console.print("[green]No issues found.[/green]\n")
        else:
            parts = []
            if errors:
                parts.append(f"[red]{errors} error{'s' if errors != 1 else ''}[/red]")
            if warnings:
                parts.append(f"[yellow]{warnings} warning{'s' if warnings != 1 else ''}[/yellow]")
            if infos:
                parts.append(f"[dim]{infos} info[/dim]")
            console.print("  " + "  ".join(parts))

        if fix and fixes_applied:
            console.print(f"\n  [green]✓[/green] {fixes_applied} auto-fix{'es' if fixes_applied != 1 else ''} applied")

        console.print()

    has_errors = any(v.severity == SEVERITY_ERROR for v in all_violations)
    if has_errors:
        raise typer.Exit(1)
