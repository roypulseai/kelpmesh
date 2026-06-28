"""Tests for kelpmesh.core.substitutions — var, env_var, is_incremental, this, Jinja blocks."""

import os
import pytest
from kelpmesh.core.substitutions import apply, parse_cli_vars


# ---------------------------------------------------------------------------
# parse_cli_vars
# ---------------------------------------------------------------------------

class TestParseCliVars:
    def test_equals_separator(self):
        assert parse_cli_vars(["start=2025-01-01"]) == {"start": "2025-01-01"}

    def test_colon_separator(self):
        assert parse_cli_vars(["start: 2025-01-01"]) == {"start": "2025-01-01"}

    def test_multiple_vars(self):
        result = parse_cli_vars(["a=1", "b=hello world"])
        assert result == {"a": "1", "b": "hello world"}

    def test_empty_list(self):
        assert parse_cli_vars([]) == {}

    def test_none_list(self):
        assert parse_cli_vars(None) == {}

    def test_value_with_equals(self):
        result = parse_cli_vars(["url=https://host/path?k=v"])
        assert result == {"url": "https://host/path?k=v"}


# ---------------------------------------------------------------------------
# {{ var() }}
# ---------------------------------------------------------------------------

class TestVarSubstitution:
    def test_simple_var(self):
        sql = "WHERE dt >= '{{ var(\"start_date\") }}'"
        result = apply(sql, vars={"start_date": "2025-01-01"})
        assert "2025-01-01" in result
        assert "{{" not in result

    def test_var_with_default(self):
        sql = "LIMIT {{ var('limit', '100') }}"
        result = apply(sql, vars={})
        assert "100" in result

    def test_var_default_overridden(self):
        sql = "LIMIT {{ var('limit', '100') }}"
        result = apply(sql, vars={"limit": "500"})
        assert "500" in result

    def test_missing_var_uses_empty_string(self):
        sql = "WHERE x = '{{ var(\"missing\") }}'"
        result = apply(sql, vars={})
        assert "x = ''" in result

    def test_single_quotes_in_template(self):
        sql = "WHERE dt >= '{{ var('start') }}'"
        result = apply(sql, vars={"start": "2025-06-01"})
        assert "2025-06-01" in result


# ---------------------------------------------------------------------------
# {{ env_var() }}
# ---------------------------------------------------------------------------

class TestEnvVarSubstitution:
    def test_env_var_present(self, monkeypatch):
        monkeypatch.setenv("MY_SCHEMA", "analytics")
        sql = "FROM {{ env_var('MY_SCHEMA') }}.orders"
        result = apply(sql)
        assert "analytics.orders" in result

    def test_env_var_missing_uses_default(self):
        os.environ.pop("KELPMESH_MISSING_VAR", None)
        sql = "SCHEMA {{ env_var('KELPMESH_MISSING_VAR', 'public') }}"
        result = apply(sql)
        assert "public" in result

    def test_env_var_missing_no_default_empty_string(self):
        os.environ.pop("KELPMESH_MISSING_VAR2", None)
        sql = "{{ env_var('KELPMESH_MISSING_VAR2') }}"
        result = apply(sql)
        assert result.strip() == ""


# ---------------------------------------------------------------------------
# {{ this }}
# ---------------------------------------------------------------------------

class TestThisSubstitution:
    def test_this_replaced(self):
        sql = "WHERE {{ this }}.id IS NOT NULL"
        result = apply(sql, table_name="my_table")
        assert "my_table.id" in result

    def test_this_no_table_name_unchanged(self):
        sql = "WHERE {{ this }}.id IS NOT NULL"
        result = apply(sql, table_name=None)
        assert "{{ this }}" in result


# ---------------------------------------------------------------------------
# {{ is_incremental() }} inline
# ---------------------------------------------------------------------------

class TestIsIncrementalInline:
    def test_inline_true(self):
        sql = "SELECT {{ is_incremental() }} AS flag"
        result = apply(sql, is_incremental=True)
        assert "TRUE" in result

    def test_inline_false(self):
        sql = "SELECT {{ is_incremental() }} AS flag"
        result = apply(sql, is_incremental=False)
        assert "FALSE" in result


# ---------------------------------------------------------------------------
# {% if is_incremental() %} blocks
# ---------------------------------------------------------------------------

class TestIsIncrementalBlocks:
    def test_block_kept_when_incremental(self):
        sql = (
            "SELECT * FROM source\n"
            "{% if is_incremental() %}\n"
            "WHERE updated_at > (SELECT MAX(updated_at) FROM {{ this }})\n"
            "{% endif %}"
        )
        result = apply(sql, is_incremental=True, table_name="orders")
        assert "WHERE updated_at" in result
        assert "{%" not in result

    def test_block_removed_when_not_incremental(self):
        sql = (
            "SELECT * FROM source\n"
            "{% if is_incremental() %}\n"
            "WHERE updated_at > '2025-01-01'\n"
            "{% endif %}"
        )
        result = apply(sql, is_incremental=False)
        assert "WHERE updated_at" not in result
        assert "{%" not in result

    def test_not_incremental_block_kept_on_first_run(self):
        sql = (
            "{% if not is_incremental() %}\n"
            "-- full refresh logic\n"
            "SELECT * FROM source\n"
            "{% endif %}"
        )
        result = apply(sql, is_incremental=False)
        assert "full refresh logic" in result
        assert "{%" not in result

    def test_not_incremental_block_removed_when_incremental(self):
        sql = (
            "{% if not is_incremental() %}\n"
            "SELECT * FROM source\n"
            "{% endif %}\n"
            "-- incremental body"
        )
        result = apply(sql, is_incremental=True)
        assert "SELECT * FROM source" not in result
        assert "incremental body" in result

    def test_whitespace_trimming_variant(self):
        sql = "{%- if is_incremental() -%}incremental_part{%- endif -%}"
        result = apply(sql, is_incremental=True)
        assert "incremental_part" in result

    def test_nested_this_inside_block(self):
        sql = (
            "{% if is_incremental() %}\n"
            "WHERE id > (SELECT MAX(id) FROM {{ this }})\n"
            "{% endif %}"
        )
        result = apply(sql, is_incremental=True, table_name="my_table")
        assert "FROM my_table" in result

    def test_block_with_var_inside(self):
        sql = (
            "{% if is_incremental() %}\n"
            "WHERE dt >= '{{ var(\"start\") }}'\n"
            "{% endif %}"
        )
        result = apply(sql, vars={"start": "2025-01-01"}, is_incremental=True)
        assert "2025-01-01" in result


# ---------------------------------------------------------------------------
# Combined expressions
# ---------------------------------------------------------------------------

class TestCombined:
    def test_full_incremental_model(self):
        sql = """
SELECT
    id,
    name,
    updated_at
FROM {{ env_var('SCHEMA', 'public') }}.orders
{% if is_incremental() %}
WHERE updated_at > (SELECT MAX(updated_at) FROM {{ this }})
{% endif %}
LIMIT {{ var('limit', '10000') }}
"""
        result = apply(
            sql,
            vars={"limit": "50000"},
            table_name="orders_daily",
            is_incremental=True,
        )
        assert "public.orders" in result
        assert "MAX(updated_at) FROM orders_daily" in result
        assert "50000" in result
        assert "{%" not in result
        assert "{{" not in result

    def test_no_substitutions_passthrough(self):
        sql = "SELECT id, name FROM orders"
        assert apply(sql) == sql
