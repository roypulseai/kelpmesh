"""SQL pre-processing: var(), env_var(), is_incremental(), this, {% if %} blocks.

Applied to every model's SQL before it is sent to the warehouse.  The
substitution order is intentional — block tags must be removed before
scalar expressions are evaluated.
"""

from __future__ import annotations

import os
import re
from typing import Any

# --------------------------------------------------------------------------- #
# Compiled regex patterns                                                      #
# --------------------------------------------------------------------------- #

# {% if is_incremental() %} ... {% endif %}  (Jinja-compatible block)
_INCR_BLOCK_RE = re.compile(
    r"\{%-?\s*if\s+is_incremental\(\)\s*-?%\}(.*?)\{%-?\s*endif\s*-?%\}",
    re.DOTALL | re.IGNORECASE,
)
# Inverse block  {% if not is_incremental() %} ... {% endif %}
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

# {{ ref("model_name") }}  — handled by keeping as-is (already resolved by parser)
# We leave ref() untouched here; it's resolved by the DAG.


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
) -> str:
    """Return *sql* with all briq template expressions substituted.

    Parameters
    ----------
    sql:
        Raw SQL read from the model file.
    vars:
        Merged variable dict (project vars + CLI --var overrides).
    table_name:
        Resolved table name for ``{{ this }}``.
    is_incremental:
        ``True`` when the target table already exists and a partial
        (incremental) run is appropriate.
    """
    vars = vars or {}

    # If a macro loader is available (macros/ dir exists), delegate to Jinja2 rendering
    # which handles macros + all built-in functions in one pass.
    if macro_loader is not None and macro_loader.has_macros:
        return macro_loader.render(
            sql,
            vars=vars,
            table_name=table_name,
            is_incremental=is_incremental,
        )

    # 1. Jinja-style block removal: {% if is_incremental() %} ... {% endif %}
    if is_incremental:
        sql = _INCR_BLOCK_RE.sub(lambda m: m.group(1), sql)
        sql = _NOT_INCR_BLOCK_RE.sub("", sql)
    else:
        sql = _INCR_BLOCK_RE.sub("", sql)
        sql = _NOT_INCR_BLOCK_RE.sub(lambda m: m.group(1), sql)

    # 2. Inline {{ is_incremental() }}
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
