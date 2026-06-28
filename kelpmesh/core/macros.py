"""SQL-native macro system.

Built-in macros are plain Python functions. Users call them with ordinary
SQL function syntax — no {{ }} or Jinja required:

    SELECT surrogate_key(order_id, customer_id) AS id,
           safe_divide(revenue, order_count)    AS avg_value
    FROM orders

The engine intercepts these calls at compile time using a sqlglot AST walk
and replaces them with the expanded SQL before the query reaches the warehouse.

Adding custom macros — two options:

  macros/my_macros.py
    from kelpmesh.core.macros import macro

    @macro("fiscal_quarter")
    def fiscal_quarter(date_col):
        return f"CONCAT('FQ', EXTRACT(QUARTER FROM {date_col}))"

  macros/my_macros.yml
    macros:
      - name: fiscal_quarter
        args: [date_col]
        sql: "CONCAT('FQ', EXTRACT(QUARTER FROM {date_col}))"

Legacy Jinja {% macro %} blocks in macros/*.sql are still supported as a
power-user escape hatch (loops, conditionals, etc.).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Callable


# --------------------------------------------------------------------------- #
# Registry                                                                     #
# --------------------------------------------------------------------------- #

_REGISTRY: dict[str, Callable[..., str]] = {}


def macro(name: str) -> Callable:
    """Decorator: register a Python function as a SQL-native macro.

    The function receives each SQL argument as a plain string and must
    return a SQL string that replaces the call site.
    """
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[name.upper()] = fn
        return fn
    return decorator


def register(name: str, fn: Callable) -> None:
    """Register a macro programmatically (used by YAML loader)."""
    _REGISTRY[name.upper()] = fn


def _registered_names() -> set[str]:
    return set(_REGISTRY.keys())


# --------------------------------------------------------------------------- #
# Built-in macros                                                              #
# --------------------------------------------------------------------------- #

@macro("surrogate_key")
def _surrogate_key(*cols: str) -> str:
    """MD5 hash of one or more columns, dash-separated.

    surrogate_key(order_id, customer_id)
    → MD5(CAST((order_id) AS VARCHAR) || '-' || CAST((customer_id) AS VARCHAR))
    """
    if not cols:
        return "MD5('')"
    parts = " || '-' || ".join(f"CAST(({c}) AS VARCHAR)" for c in cols)
    return f"MD5({parts})"


@macro("safe_divide")
def _safe_divide(numerator: str, denominator: str, default: str = "0") -> str:
    """Division that returns *default* instead of dividing by zero.

    safe_divide(revenue, orders)
    → CASE WHEN (orders) = 0 OR (orders) IS NULL THEN 0 ELSE (revenue) / (orders) END
    """
    return (
        f"CASE WHEN ({denominator}) = 0 OR ({denominator}) IS NULL "
        f"THEN {default} ELSE ({numerator}) / ({denominator}) END"
    )


@macro("datediff")
def _datediff(datepart: str, start: str, end: str) -> str:
    """Date difference with consistent cross-warehouse syntax.

    datediff('day', start_date, end_date)
    → DATEDIFF('day', start_date, end_date)
    """
    return f"DATEDIFF({datepart}, {start}, {end})"


@macro("nullif_empty")
def _nullif_empty(col: str) -> str:
    """Convert empty string to NULL.

    nullif_empty(email) → NULLIF(TRIM(email), '')
    """
    return f"NULLIF(TRIM({col}), '')"


@macro("coalesce_zero")
def _coalesce_zero(col: str) -> str:
    """Replace NULL with 0.

    coalesce_zero(revenue) → COALESCE(revenue, 0)
    """
    return f"COALESCE({col}, 0)"


# --------------------------------------------------------------------------- #
# String-based expansion                                                       #
# --------------------------------------------------------------------------- #
#
# We use a lightweight recursive-descent string parser rather than an AST
# library.  The reason: SQL AST parsers (including sqlglot) classify some of
# our macro names as known SQL functions for specific dialects (e.g. sqlglot
# treats safe_divide as a BigQuery built-in, datediff as a known Func), so
# they never appear as "anonymous" calls in the tree and cannot be caught by
# a generic transformer.  The string parser is dialect-agnostic and matches
# any word followed by '(' that appears in the registry.

def expand_macros(sql: str, dialect: str | None = None) -> str:
    """Expand SQL-native macro calls in *sql*.

    Scans the SQL string for ``name(args)`` patterns where ``name`` is a
    registered macro, extracts arguments respecting nested parentheses and
    string literals, calls the Python function, and substitutes the result
    inline.  Falls back to the original string on any error.
    """
    if not _REGISTRY or not sql:
        return sql

    # Fast pre-check: skip scanning if no registry name appears in the SQL.
    sql_upper = sql.upper()
    if not any(name in sql_upper for name in _REGISTRY):
        return sql

    return _expand_string(sql)


def _expand_string(sql: str) -> str:
    """Recursive worker: expand all macro calls in *sql*."""
    result: list[str] = []
    i = 0
    n = len(sql)

    while i < n:
        c = sql[i]

        # ── Skip string literals ───────────────────────────────────────────
        if c in ("'", '"'):
            j = i + 1
            while j < n:
                if sql[j] == '\\':
                    j += 2
                    continue
                if sql[j] == c:
                    j += 1
                    break
                j += 1
            result.append(sql[i:j])
            i = j
            continue

        # ── Skip line comments  (-- …) ────────────────────────────────────
        if sql[i:i + 2] == '--':
            j = sql.find('\n', i)
            end = n if j == -1 else j + 1
            result.append(sql[i:end])
            i = end
            continue

        # ── Skip block comments  (/* … */) ────────────────────────────────
        if sql[i:i + 2] == '/*':
            j = sql.find('*/', i + 2)
            end = n if j == -1 else j + 2
            result.append(sql[i:end])
            i = end
            continue

        # ── Identifier start ───────────────────────────────────────────────
        if c.isalpha() or c == '_':
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] == '_'):
                j += 1
            name = sql[i:j]

            # Skip whitespace between name and potential '('
            k = j
            while k < n and sql[k] == ' ':
                k += 1

            if k < n and sql[k] == '(' and name.upper() in _REGISTRY:
                paren_end, raw_args_str = _find_closing_paren(sql, k)
                if paren_end != -1:
                    # Split and recursively expand args
                    args = [_expand_string(a.strip()) for a in _split_args(raw_args_str)]
                    fn = _REGISTRY[name.upper()]
                    try:
                        expanded = fn(*args)
                        result.append(expanded)
                        i = paren_end + 1
                        continue
                    except Exception:
                        pass  # expansion failed — emit original call unchanged

            result.append(sql[i:j])
            i = j
            continue

        result.append(c)
        i += 1

    return ''.join(result)


def _find_closing_paren(sql: str, open_pos: int) -> tuple[int, str]:
    """Return (close_pos, content) for the paren starting at *open_pos*."""
    depth = 1
    i = open_pos + 1
    n = len(sql)
    while i < n and depth > 0:
        c = sql[i]
        if c in ("'", '"'):
            j = i + 1
            while j < n:
                if sql[j] == '\\':
                    j += 2
                    continue
                if sql[j] == c:
                    break
                j += 1
            i = j + 1
            continue
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return i, sql[open_pos + 1:i]
        i += 1
    return -1, ""


def _split_args(args_str: str) -> list[str]:
    """Split top-level comma-separated arguments (respects nested parens)."""
    args: list[str] = []
    depth = 0
    buf: list[str] = []
    for c in args_str:
        if c == '(':
            depth += 1
            buf.append(c)
        elif c == ')':
            depth -= 1
            buf.append(c)
        elif c == ',' and depth == 0:
            args.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(c)
    last = ''.join(buf).strip()
    if last:
        args.append(last)
    return args


# --------------------------------------------------------------------------- #
# MacroLoader — discovers macros/ directory at project init                   #
# --------------------------------------------------------------------------- #

class MacroLoader:
    """Loads user-defined macros from macros/*.py and macros/*.yml.

    Built-in macros are always available via the module-level registry.
    This class handles the user-defined layer on top.
    """

    def __init__(self) -> None:
        self._user_count: int = 0
        self._jinja_src: str = ""   # legacy Jinja {% macro %} blocks

    def load_dirs(self, dirs: list[Path]) -> None:
        for d in dirs:
            if not isinstance(d, Path):
                d = Path(d)
            if not d.exists():
                continue
            for f in sorted(d.rglob("*.py")):
                self._load_python(f)
            for f in sorted(d.rglob("*.yml")):
                self._load_yaml(f)
            for f in sorted(d.rglob("*.yaml")):
                self._load_yaml(f)
            # Legacy: Jinja-style *.sql macro files (power-user escape hatch)
            for f in sorted(d.rglob("*.sql")):
                text = f.read_text(encoding="utf-8").strip()
                if text and "{%" in text:
                    self._jinja_src += "\n\n" + text

    def _load_python(self, path: Path) -> None:
        spec = importlib.util.spec_from_file_location(
            f"_kelpmesh_macros_{path.stem}", path
        )
        if spec is None or spec.loader is None:
            return
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            self._user_count += 1
        except Exception:
            pass

    def _load_yaml(self, path: Path) -> None:
        try:
            import yaml
        except ImportError:
            return
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return
        for defn in (data or {}).get("macros", []):
            name = defn.get("name", "")
            args = defn.get("args", [])
            sql_tpl = defn.get("sql", "")
            if name and sql_tpl:
                def _make(tpl: str, arg_names: list) -> Callable:
                    def _fn(*positional: str) -> str:
                        kwargs = dict(zip(arg_names, positional))
                        return tpl.format(**kwargs)
                    return _fn
                register(name, _make(sql_tpl, list(args)))
                self._user_count += 1

    @property
    def has_macros(self) -> bool:
        return True  # built-ins are always registered

    @property
    def has_jinja_macros(self) -> bool:
        """True only when legacy Jinja {% macro %} SQL files were found."""
        return bool(self._jinja_src.strip())

    def expand(self, sql: str, dialect: str | None = None) -> str:
        """Expand SQL-native macro calls."""
        return expand_macros(sql, dialect=dialect)

    def render_jinja(
        self,
        sql: str,
        *,
        vars: dict | None = None,
        table_name: str | None = None,
        is_incremental: bool = False,
    ) -> str:
        """Jinja2 rendering path — only used for legacy {% macro %} SQL files."""
        import os
        from jinja2 import Undefined
        from jinja2.sandbox import SandboxedEnvironment

        env = SandboxedEnvironment(
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=Undefined,
        )
        vars = vars or {}
        context = {
            "var": lambda n, d="": str(vars.get(n, d)),
            "env_var": lambda n, d="": os.environ.get(n, d),
            "is_incremental": lambda: is_incremental,
            "this": table_name or "",
        }
        full_src = (self._jinja_src + "\n\n" + sql) if self._jinja_src else sql
        try:
            return env.from_string(full_src).render(**context)
        except Exception:
            return sql


# --------------------------------------------------------------------------- #
# Module-level singleton                                                       #
# --------------------------------------------------------------------------- #

_global_loader: MacroLoader = MacroLoader()


def get_loader() -> MacroLoader:
    return _global_loader


def load_macros(dirs: list[Path]) -> None:
    """Load user-defined macros from one or more directories."""
    _global_loader.load_dirs(dirs)


def load_builtins() -> None:
    """No-op — built-ins register themselves at import time via @macro."""
    pass
