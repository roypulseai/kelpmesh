"""SQL-native macro system — 32 built-in macros, zero {{ }} syntax required.

Users write plain SQL function calls; the engine expands them at compile time:

    SELECT surrogate_key(order_id, customer_id) AS id,
           safe_divide(revenue, orders)          AS avg_rev,
           median(session_duration)              AS p50,
           haversine(lat1, lon1, lat2, lon2)     AS dist_km
    FROM orders

Adding custom macros — two options:

  macros/my_macros.py
    from kelpmesh.core.macros import macro

    @macro("fiscal_quarter")
    def fiscal_quarter(date_col, offset="3"):
        return f"CONCAT('FQ', EXTRACT(QUARTER FROM DATEADD(month, {offset}, {date_col})))"

  macros/my_macros.yml
    macros:
      - name: fiscal_quarter
        args: [date_col]
        sql: "CONCAT('FQ', EXTRACT(QUARTER FROM {date_col}))"

Legacy Jinja {% macro %} blocks in macros/*.sql are still supported as a
power-user escape hatch (loops, conditionals, etc.).
"""

from __future__ import annotations

__all__ = [
    "macro",
    "register",
    "expand_macros",
    "MacroLoader",
    "get_loader",
    "load_macros",
    "load_builtins",
]

import importlib.util
from pathlib import Path
from typing import Callable

# ─────────────────────────────────────────────────────────────────────────── #
# Registry                                                                     #
# ─────────────────────────────────────────────────────────────────────────── #

_REGISTRY: dict[str, Callable[..., str]] = {}


def macro(name: str) -> Callable:
    """Decorator: register a Python function as a SQL-native macro."""
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[name.upper()] = fn
        return fn
    return decorator


def register(name: str, fn: Callable) -> None:
    """Register a macro programmatically (used by YAML loader)."""
    _REGISTRY[name.upper()] = fn


def _registered_names() -> set[str]:
    return set(_REGISTRY.keys())


# ─────────────────────────────────────────────────────────────────────────── #
# Built-in macros — hashing & keys                                             #
# ─────────────────────────────────────────────────────────────────────────── #

@macro("surrogate_key")
def _surrogate_key(*cols: str) -> str:
    """MD5 of one or more columns, dash-separated.
    surrogate_key(order_id, customer_id)
    """
    if not cols:
        return "MD5('')"
    parts = " || '-' || ".join(f"CAST(({c}) AS VARCHAR)" for c in cols)
    return f"MD5({parts})"


@macro("generate_surrogate_key")
def _generate_surrogate_key(*cols: str) -> str:
    """Alias for surrogate_key — dbt-utils compatibility."""
    return _surrogate_key(*cols)


@macro("hash_record")
def _hash_record(*cols: str) -> str:
    """MD5 of all supplied columns concatenated with '|' separator.
    hash_record(col_a, col_b, col_c)
    """
    if not cols:
        return "MD5('')"
    parts = " || '|' || ".join(f"COALESCE(CAST(({c}) AS VARCHAR), '')" for c in cols)
    return f"MD5({parts})"


# ─────────────────────────────────────────────────────────────────────────── #
# Built-in macros — arithmetic & null-safety                                   #
# ─────────────────────────────────────────────────────────────────────────── #

@macro("safe_divide")
def _safe_divide(numerator: str, denominator: str, default: str = "0") -> str:
    """Division that returns *default* instead of erroring on zero.
    safe_divide(revenue, orders)
    safe_divide(revenue, orders, -1)
    """
    return (
        f"CASE WHEN ({denominator}) = 0 OR ({denominator}) IS NULL "
        f"THEN {default} ELSE ({numerator}) / ({denominator}) END"
    )


@macro("div0")
def _div0(numerator: str, denominator: str) -> str:
    """Snowflake-style DIV0 — returns 0 on division by zero.
    div0(revenue, order_count)
    """
    return _safe_divide(numerator, denominator, "0")


@macro("iff")
def _iff(condition: str, true_val: str, false_val: str) -> str:
    """Single-condition ternary — Snowflake IFF() equivalent.
    iff(status = 'active', 1, 0)
    """
    return f"CASE WHEN {condition} THEN {true_val} ELSE {false_val} END"


@macro("ifnull")
def _ifnull(col: str, default: str) -> str:
    """Replace NULL with *default* — COALESCE alias.
    ifnull(revenue, 0)
    """
    return f"COALESCE({col}, {default})"


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


@macro("zeroifnull")
def _zeroifnull(col: str) -> str:
    """Alias for coalesce_zero — Snowflake zeroifnull() compatibility.
    zeroifnull(amount)
    """
    return f"COALESCE({col}, 0)"


@macro("nullifzero")
def _nullifzero(col: str) -> str:
    """Convert 0 to NULL — inverse of zeroifnull.
    nullifzero(order_count)
    """
    return f"NULLIF({col}, 0)"


# ─────────────────────────────────────────────────────────────────────────── #
# Built-in macros — date & time                                                #
# ─────────────────────────────────────────────────────────────────────────── #

@macro("datediff")
def _datediff(datepart: str, start: str, end: str) -> str:
    """Cross-warehouse date difference.
    datediff('day', start_date, end_date)
    """
    return f"DATEDIFF({datepart}, {start}, {end})"


@macro("dateadd")
def _dateadd(datepart: str, n: str, date: str) -> str:
    """Add an interval to a date — cross-warehouse.
    dateadd('month', 3, order_date)
    """
    return f"DATEADD({datepart}, {n}, {date})"


@macro("date_trunc")
def _date_trunc(datepart: str, date: str) -> str:
    """Truncate a date to the specified period.
    date_trunc('month', event_date)
    """
    return f"DATE_TRUNC({datepart}, {date})"


@macro("last_day")
def _last_day(date: str) -> str:
    """Last day of the month for a given date.
    last_day(order_date)
    """
    return f"LAST_DAY({date})"


@macro("week_start")
def _week_start(date: str) -> str:
    """First day of the ISO week containing *date*.
    week_start(event_date)
    """
    return f"DATE_TRUNC('week', {date})"


@macro("quarter_start")
def _quarter_start(date: str) -> str:
    """First day of the quarter containing *date*.
    quarter_start(transaction_date)
    """
    return f"DATE_TRUNC('quarter', {date})"


@macro("year_month")
def _year_month(date: str) -> str:
    """Return YYYYMM as an integer — useful for partition keys.
    year_month(created_at) → e.g. 202406
    """
    return (
        f"CAST(EXTRACT(YEAR FROM {date}) AS INTEGER) * 100 "
        f"+ CAST(EXTRACT(MONTH FROM {date}) AS INTEGER)"
    )


@macro("age_in_days")
def _age_in_days(start_date: str, end_date: str) -> str:
    """Number of days between two dates.
    age_in_days(signup_date, CURRENT_DATE)
    """
    return f"DATEDIFF('day', {start_date}, {end_date})"


@macro("current_utc")
def _current_utc() -> str:
    """Current timestamp in UTC — cross-warehouse.
    current_utc()
    """
    return "CURRENT_TIMESTAMP"


# ─────────────────────────────────────────────────────────────────────────── #
# Built-in macros — string                                                     #
# ─────────────────────────────────────────────────────────────────────────── #

@macro("initcap")
def _initcap(col: str) -> str:
    """Title-case a string — maps to INITCAP() where available.
    initcap(customer_name)
    """
    return f"INITCAP({col})"


@macro("regexp_extract")
def _regexp_extract(col: str, pattern: str, group: str = "1") -> str:
    """Extract a captured group from a regex match.
    regexp_extract(url, 'utm_source=([^&]+)', 1)
    """
    return f"REGEXP_EXTRACT({col}, {pattern}, {group})"


@macro("email_domain")
def _email_domain(email_col: str) -> str:
    """Extract the domain portion from an email address.
    email_domain(user_email) → 'example.com'
    """
    return f"SUBSTRING({email_col} FROM POSITION('@' IN {email_col}) + 1)"


@macro("phone_digits")
def _phone_digits(col: str) -> str:
    """Strip all non-digit characters from a phone number column.
    phone_digits(phone_number) → '14155551234'
    """
    return f"REGEXP_REPLACE({col}, '[^0-9]', '')"


@macro("left_pad")
def _left_pad(col: str, length: str, pad_char: str = "'0'") -> str:
    """Left-pad a string to *length* with *pad_char*.
    left_pad(month_num, 2, '0')
    """
    return f"LPAD(CAST({col} AS VARCHAR), {length}, {pad_char})"


@macro("right_pad")
def _right_pad(col: str, length: str, pad_char: str = "' '") -> str:
    """Right-pad a string to *length* with *pad_char*.
    right_pad(code, 10)
    """
    return f"RPAD(CAST({col} AS VARCHAR), {length}, {pad_char})"


@macro("contains")
def _contains(col: str, substr: str) -> str:
    """True if *substr* appears anywhere in *col*.
    contains(description, 'urgent')
    """
    return f"POSITION({substr} IN {col}) > 0"


@macro("is_valid_email")
def _is_valid_email(col: str) -> str:
    """Regex check for a valid-looking email address.
    is_valid_email(email_col)
    """
    pattern = r"'^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$'"
    return f"REGEXP_LIKE({col}, {pattern})"


@macro("url_extract_host")
def _url_extract_host(url_col: str) -> str:
    """Extract the hostname from a URL string.
    url_extract_host(page_url) → 'example.com'
    """
    return (
        f"REGEXP_EXTRACT({url_col}, "
        f"'https?://([^/\\?#]+)', 1)"
    )


# ─────────────────────────────────────────────────────────────────────────── #
# Built-in macros — aggregation & statistics                                   #
# ─────────────────────────────────────────────────────────────────────────── #

@macro("median")
def _median(col: str) -> str:
    """Median value — PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY col).
    median(response_time_ms)
    """
    return f"PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {col})"


@macro("percentile")
def _percentile(col: str, p: str) -> str:
    """Exact percentile via PERCENTILE_CONT.
    percentile(latency_ms, 0.95)  -- p95
    """
    return f"PERCENTILE_CONT({p}) WITHIN GROUP (ORDER BY {col})"


# ─────────────────────────────────────────────────────────────────────────── #
# Built-in macros — geospatial                                                 #
# ─────────────────────────────────────────────────────────────────────────── #

@macro("haversine")
def _haversine(lat1: str, lon1: str, lat2: str, lon2: str) -> str:
    """Great-circle distance in kilometres between two lat/lon points.
    haversine(pickup_lat, pickup_lon, dropoff_lat, dropoff_lon)
    """
    return (
        f"2 * 6371 * ASIN(SQRT("
        f"  POWER(SIN((RADIANS({lat2}) - RADIANS({lat1})) / 2), 2)"
        f"  + COS(RADIANS({lat1})) * COS(RADIANS({lat2}))"
        f"    * POWER(SIN((RADIANS({lon2}) - RADIANS({lon1})) / 2), 2)"
        f"))"
    )


# ─────────────────────────────────────────────────────────────────────────── #
# String-based expansion engine                                                #
# ─────────────────────────────────────────────────────────────────────────── #
#
# We use a recursive-descent string parser rather than an AST library.
# Reason: sqlglot classifies some macro names as known dialect functions
# (safe_divide → BigQuery SafeDivide, datediff → DateDiff) and they never
# appear as Anonymous nodes, so an AST transformer silently skips them.
# The string parser is dialect-agnostic and catches everything in the registry.

def expand_macros(sql: str, dialect: str | None = None) -> str:
    """Expand SQL-native macro calls in *sql*.

    Scans for ``name(args)`` where ``name`` is a registered macro, extracts
    arguments respecting nested parens and string literals, calls the Python
    function, and substitutes the result inline.  Falls back to original on
    any error.
    """
    if not _REGISTRY or not sql:
        return sql

    sql_upper = sql.upper()
    if not any(name in sql_upper for name in _REGISTRY):
        return sql

    return _expand_string(sql)


def _expand_string(sql: str) -> str:
    result: list[str] = []
    i = 0
    n = len(sql)

    while i < n:
        c = sql[i]

        # skip string literals
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

        # skip line comments
        if sql[i:i + 2] == '--':
            j = sql.find('\n', i)
            end = n if j == -1 else j + 1
            result.append(sql[i:end])
            i = end
            continue

        # skip block comments
        if sql[i:i + 2] == '/*':
            j = sql.find('*/', i + 2)
            end = n if j == -1 else j + 2
            result.append(sql[i:end])
            i = end
            continue

        # identifier start
        if c.isalpha() or c == '_':
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] == '_'):
                j += 1
            name = sql[i:j]

            k = j
            while k < n and sql[k] == ' ':
                k += 1

            if k < n and sql[k] == '(' and name.upper() in _REGISTRY:
                paren_end, raw_args_str = _find_closing_paren(sql, k)
                if paren_end != -1:
                    args = [_expand_string(a.strip()) for a in _split_args(raw_args_str)]
                    fn = _REGISTRY[name.upper()]
                    try:
                        expanded = fn(*args)
                        result.append(expanded)
                        i = paren_end + 1
                        continue
                    except Exception:
                        pass

            result.append(sql[i:j])
            i = j
            continue

        result.append(c)
        i += 1

    return ''.join(result)


def _find_closing_paren(sql: str, open_pos: int) -> tuple[int, str]:
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


# ─────────────────────────────────────────────────────────────────────────── #
# MacroLoader — discovers project macros/ directory                            #
# ─────────────────────────────────────────────────────────────────────────── #

class MacroLoader:
    """Loads user-defined macros from macros/*.py and macros/*.yml.

    Built-in macros are always available via the module-level registry.
    This class handles the user-defined layer on top.
    """

    def __init__(self) -> None:
        self._user_count: int = 0
        self._jinja_src: str = ""

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
        return True

    @property
    def has_jinja_macros(self) -> bool:
        return bool(self._jinja_src.strip())

    def expand(self, sql: str, dialect: str | None = None) -> str:
        return expand_macros(sql, dialect=dialect)

    def render_jinja(
        self,
        sql: str,
        *,
        vars: dict | None = None,
        table_name: str | None = None,
        is_incremental: bool = False,
    ) -> str:
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


# ─────────────────────────────────────────────────────────────────────────── #
# Module-level singleton                                                       #
# ─────────────────────────────────────────────────────────────────────────── #

_global_loader: MacroLoader = MacroLoader()


def get_loader() -> MacroLoader:
    return _global_loader


def load_macros(dirs: list[Path]) -> None:
    _global_loader.load_dirs(dirs)


def load_builtins() -> None:
    """No-op — built-ins register themselves at import time via @macro."""
    pass


# ─────────────────────────────────────────────────────────────────────────── #
# dbt compatibility macros                                                     #
#                                                                              #
# These let dbt users write common dbt/dbt_utils macro names as plain SQL     #
# function calls (no Jinja). They expand to native SQL at compile time.       #
#                                                                              #
# Example:  SELECT cents_to_dollars(revenue_cents) AS revenue_dollars         #
#           → SELECT (revenue_cents / 100)::numeric(16, 2) AS revenue_dollars  #
# ─────────────────────────────────────────────────────────────────────────── #


@macro("cents_to_dollars")
def _cents_to_dollars(column: str) -> str:
    """dbt macro: convert cents to dollars.
    cents_to_dollars(revenue_cents) → (revenue_cents / 100)::numeric(16, 2)
    """
    return f"({column} / 100)::numeric(16, 2)"


@macro("dollars_to_cents")
def _dollars_to_cents(column: str) -> str:
    """Inverse of cents_to_dollars.
    dollars_to_cents(revenue) → (revenue * 100)::bigint
    """
    return f"({column} * 100)::bigint"


@macro("dbt_current_timestamp")
def _dbt_current_timestamp() -> str:
    """dbt.current_timestamp() → CURRENT_TIMESTAMP"""
    return "CURRENT_TIMESTAMP"


@macro("dbt_now")
def _dbt_now() -> str:
    """dbt.now() → CURRENT_TIMESTAMP (alias)"""
    return "CURRENT_TIMESTAMP"


@macro("dbt_type_string")
def _dbt_type_string() -> str:
    """dbt.type_string() → 'VARCHAR'"""
    return "'VARCHAR'"


@macro("dbt_type_numeric")
def _dbt_type_numeric() -> str:
    """dbt.type_numeric() → 'DECIMAL'"""
    return "'DECIMAL'"


@macro("dbt_type_bigint")
def _dbt_type_bigint() -> str:
    """dbt.type_bigint() → 'BIGINT'"""
    return "'BIGINT'"


@macro("dbt_type_int")
def _dbt_type_int() -> str:
    """dbt.type_int() → 'INTEGER'"""
    return "'INTEGER'"


@macro("dbt_type_timestamp")
def _dbt_type_timestamp() -> str:
    """dbt.type_timestamp() → 'TIMESTAMP'"""
    return "'TIMESTAMP'"


@macro("dbt_type_date")
def _dbt_type_date() -> str:
    """dbt.type_date() → 'DATE'"""
    return "'DATE'"


@macro("dbt_type_boolean")
def _dbt_type_boolean() -> str:
    """dbt.type_boolean() → 'BOOLEAN'"""
    return "'BOOLEAN'"


@macro("dbt_type_float")
def _dbt_type_float() -> str:
    """dbt.type_float() → 'DOUBLE'"""
    return "'DOUBLE'"
