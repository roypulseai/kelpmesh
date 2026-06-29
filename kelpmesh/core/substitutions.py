"""SQL pre-processing: var(), env_var(), is_incremental(), this, macro expansion.

Processing order per model:
  1. {% if is_incremental() %} blocks  (regex — no Jinja dep)
  2. {{ is_incremental() }}            (regex)
  3. {{ this }}                        (regex)
  4. {{ var("name") }}                 (regex)
  5. {{ env_var("NAME") }}             (regex)
  6. SQL-native macro calls            (sqlglot AST — surrogate_key(), safe_divide(), …)

If the macros/ directory contains legacy Jinja {% macro %} SQL files, steps
1-6 are replaced by a single Jinja2 SandboxedEnvironment render so that the
Jinja blocks and SQL-native calls are all handled together.
"""

from __future__ import annotations

import os
import re
from typing import Any

# --------------------------------------------------------------------------- #
# Compiled regex patterns                                                      #
# --------------------------------------------------------------------------- #

# {% if is_incremental() %} ... {% endif %}
_INCR_BLOCK_RE = re.compile(
    r"\{%-?\s*if\s+is_incremental\(\)\s*-?%\}(.*?)\{%-?\s*endif\s*-?%\}",
    re.DOTALL | re.IGNORECASE,
)
# {% if not is_incremental() %} ... {% endif %}
_NOT_INCR_BLOCK_RE = re.compile(
    r"\{%-?\s*if\s+not\s+is_incremental\(\)\s*-?%\}(.*?)\{%-?\s*endif\s*-?%\}",
    re.DOTALL | re.IGNORECASE,
)

# {{ is_incremental() }}  (inline scalar)
_IS_INCR_INLINE_RE = re.compile(r"\{\{\s*is_incremental\(\)\s*\}\}")

# {{ var("name") }}  or  {{ var("name", "default") }}
_VAR_RE = re.compile(
    r"\{\{\s*var\(['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]([^'\"]*)['\"])?\s*\)\s*\}\}"
)

# {{ env_var("NAME") }}  or  {{ env_var("NAME", "default") }}
_ENV_VAR_RE = re.compile(
    r"\{\{\s*env_var\(['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]([^'\"]*)['\"])?\s*\)\s*\}\}"
)

# {{ this }}
_THIS_RE = re.compile(r"\{\{\s*this\s*\}\}")


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def apply(
    sql: str,
    *,
    vars: dict[str, Any] | None = None,
    table_name: str | None = None,
    is_incremental: bool = False,
    macro_loader=None,
    dialect: str | None = None,
) -> str:
    """Return *sql* with all KelpMesh template expressions substituted.

    Parameters
    ----------
    sql:
        Raw SQL read from the model file.
    vars:
        Merged variable dict (project vars + CLI --var overrides).
    table_name:
        Resolved table name for ``{{ this }}``.
    is_incremental:
        True when the target table already exists and a partial run is wanted.
    macro_loader:
        MacroLoader instance from the project. When it contains legacy Jinja
        {% macro %} SQL files, the whole rendering is delegated to Jinja2.
    dialect:
        sqlglot dialect name (e.g. ``"bigquery"``, ``"snowflake"``). Used for
        SQL-native macro expansion so the output matches warehouse syntax.
    """
    vars = vars or {}

    # Legacy path: if the project has Jinja {% macro %} .sql files, hand off
    # to Jinja2 which handles both {{ }} substitutions and macro calls in one pass.
    if macro_loader is not None and macro_loader.has_jinja_macros:
        return macro_loader.render_jinja(
            sql,
            vars=vars,
            table_name=table_name,
            is_incremental=is_incremental,
        )

    # ── Standard path ────────────────────────────────────────────────────────

    # 1. {% if is_incremental() %} ... {% endif %}
    if is_incremental:
        sql = _INCR_BLOCK_RE.sub(lambda m: m.group(1), sql)
        sql = _NOT_INCR_BLOCK_RE.sub("", sql)
    else:
        sql = _INCR_BLOCK_RE.sub("", sql)
        sql = _NOT_INCR_BLOCK_RE.sub(lambda m: m.group(1), sql)

    # 2. {{ is_incremental() }}
    sql = _IS_INCR_INLINE_RE.sub("TRUE" if is_incremental else "FALSE", sql)

    # 3. {{ this }}
    if table_name:
        sql = _THIS_RE.sub(table_name, sql)

    # 4. {{ var("name") }} / {{ var("name", "default") }}
    def _var_sub(m: re.Match) -> str:
        key, default = m.group(1), m.group(2) or ""
        return str(vars.get(key, default))

    sql = _VAR_RE.sub(_var_sub, sql)

    # 5. {{ env_var("NAME") }} / {{ env_var("NAME", "default") }}
    def _env_sub(m: re.Match) -> str:
        key, default = m.group(1), m.group(2) or ""
        return os.environ.get(key, default)

    sql = _ENV_VAR_RE.sub(_env_sub, sql)

    # 6. SQL-native macro expansion — always runs (built-ins are always registered).
    #    surrogate_key(a, b) → MD5(CAST((a) AS VARCHAR) || '-' || CAST((b) AS VARCHAR))
    from kelpmesh.core.macros import expand_macros
    sql = expand_macros(sql, dialect=dialect)

    return sql


def parse_cli_vars(var_args: list[str]) -> dict[str, str]:
    """Parse ``--var key=value`` CLI arguments into a dict.

    Supports both ``key=value`` and ``key: value`` formats.
    """
    result: dict[str, str] = {}
    for item in var_args or []:
        item = item.strip()
        for sep in ("=", ":"):
            if sep in item:
                k, v = item.split(sep, 1)
                result[k.strip()] = v.strip()
                break
    return result


class SubstitutionEngine:
    """Apply var(), env_var(), is_incremental(), and macro substitutions to SQL."""

    @staticmethod
    def apply(sql: str, vars: dict[str, str] | None = None,
              env: dict[str, str] | None = None,
              is_incremental: bool = False, dialect: str = "duckdb") -> str:
        return apply(sql, vars=vars, env=env, is_incremental=is_incremental, dialect=dialect)
