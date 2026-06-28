"""Macro system — load reusable SQL macros from macros/*.sql and expand them.

Macros use dbt-compatible syntax:

    {% macro surrogate_key(columns) %}
        md5(concat_ws('||', {% for col in columns %}cast({{ col }} as varchar){% endfor %}))
    {% endmacro %}

Called in models as:

    SELECT {{ surrogate_key(['order_id', 'customer_id']) }} AS sk

Rendering uses Jinja2 SandboxedEnvironment — no filesystem access or Python
builtins are available inside macro bodies.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from jinja2 import Undefined
from jinja2.sandbox import SandboxedEnvironment


_JINJA_OPTS = dict(
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=Undefined,
)


class MacroLoader:
    """Loads macro definitions and renders model SQL with full Jinja2 support."""

    def __init__(self) -> None:
        self._macro_src: str = ""
        self._env = SandboxedEnvironment(**_JINJA_OPTS)

    def load_dirs(self, dirs: list[Path]) -> None:
        parts: list[str] = []
        for d in dirs:
            if not isinstance(d, Path):
                d = Path(d)
            if not d.exists():
                continue
            for f in sorted(d.rglob("*.sql")):
                text = f.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(text)
        self._macro_src = "\n\n".join(parts)

    @property
    def has_macros(self) -> bool:
        return bool(self._macro_src.strip())

    def render(
        self,
        sql: str,
        *,
        vars: dict[str, Any] | None = None,
        table_name: str | None = None,
        is_incremental: bool = False,
    ) -> str:
        """Render model SQL with macros + built-in functions available."""
        vars = vars or {}

        def _var(name: str, default: str = "") -> str:
            return str(vars.get(name, default))

        def _env_var(name: str, default: str = "") -> str:
            return os.environ.get(name, default)

        def _is_incremental() -> bool:
            return is_incremental

        context: dict[str, Any] = {
            "var": _var,
            "env_var": _env_var,
            "is_incremental": _is_incremental,
            "this": table_name or "",
        }

        # Prepend macro definitions so they're in scope for the model SQL
        full_src = (self._macro_src + "\n\n" + sql) if self._macro_src else sql

        try:
            tmpl = self._env.from_string(full_src)
            return tmpl.render(**context)
        except Exception:
            # If Jinja2 rendering fails (e.g. undefined macro), fall through to
            # the regex-based substitutions path by returning the original SQL.
            return sql


# Module-level singleton populated by project.py at load time
_global_loader: MacroLoader = MacroLoader()


def get_loader() -> MacroLoader:
    return _global_loader


def load_macros(dirs: list[Path]) -> None:
    """Load macros from one or more directories into the global loader."""
    _global_loader.load_dirs(dirs)


# Convenience: built-in macros shipped with kelpmesh (no macros/ dir required)
BUILTIN_MACROS = """\
{% macro surrogate_key(columns) -%}
md5(concat_ws('||', {% for col in columns %}cast({{ col }} as varchar){% if not loop.last %}, {% endif %}{% endfor %}))
{%- endmacro %}

{% macro safe_divide(numerator, denominator, default=0) -%}
case when ({{ denominator }}) = 0 then {{ default }} else ({{ numerator }}) / ({{ denominator }}) end
{%- endmacro %}

{% macro date_trunc(period, column) -%}
date_trunc('{{ period }}', {{ column }})
{%- endmacro %}

{% macro current_timestamp() -%}
current_timestamp
{%- endmacro %}

{% macro datediff(datepart, start, end) -%}
datediff('{{ datepart }}', {{ start }}, {{ end }})
{%- endmacro %}

{% macro generate_schema_name(schema) -%}
{{ schema }}
{%- endmacro %}
"""


def load_builtins() -> None:
    """Register built-in utility macros — always available without a macros/ dir."""
    existing = _global_loader._macro_src
    _global_loader._macro_src = BUILTIN_MACROS + "\n\n" + existing
