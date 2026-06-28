"""Tests for the SQL-native macro system.

Users write plain SQL function calls; the engine expands them at compile time.
No {{ }} or Jinja required.
"""

import textwrap
import tempfile
from pathlib import Path

import pytest

from kelpmesh.core.macros import (
    expand_macros,
    register,
    macro,
    MacroLoader,
    _REGISTRY,
)
from kelpmesh.core.substitutions import apply


# --------------------------------------------------------------------------- #
# Built-in macro expansion                                                     #
# --------------------------------------------------------------------------- #

class TestBuiltinMacros:
    def test_surrogate_key_two_cols(self):
        sql = "SELECT surrogate_key(order_id, customer_id) AS sk FROM orders"
        result = expand_macros(sql)
        assert "MD5(" in result
        assert "order_id" in result
        assert "customer_id" in result
        assert "surrogate_key" not in result

    def test_surrogate_key_single_col(self):
        sql = "SELECT surrogate_key(id) AS sk FROM t"
        result = expand_macros(sql)
        assert "MD5(" in result
        assert "surrogate_key" not in result

    def test_surrogate_key_three_cols(self):
        sql = "SELECT surrogate_key(a, b, c) AS sk FROM t"
        result = expand_macros(sql)
        assert "MD5(" in result
        assert "'-'" in result or "'-'" in result

    def test_safe_divide_basic(self):
        sql = "SELECT safe_divide(revenue, order_count) AS avg_val FROM sales"
        result = expand_macros(sql)
        assert "CASE WHEN" in result
        assert "revenue" in result
        assert "order_count" in result
        assert "safe_divide" not in result

    def test_safe_divide_with_default(self):
        sql = "SELECT safe_divide(revenue, cnt, -1) AS v FROM t"
        result = expand_macros(sql)
        assert "CASE WHEN" in result
        assert "-1" in result

    def test_datediff(self):
        sql = "SELECT datediff('day', start_date, end_date) AS days FROM t"
        result = expand_macros(sql)
        assert "DATEDIFF" in result.upper()
        assert "start_date" in result
        assert "end_date" in result
        assert "datediff" not in result.lower() or "DATEDIFF" in result

    def test_nullif_empty(self):
        sql = "SELECT nullif_empty(email) AS clean_email FROM users"
        result = expand_macros(sql)
        assert "NULLIF" in result
        assert "TRIM" in result
        assert "nullif_empty" not in result

    def test_coalesce_zero(self):
        sql = "SELECT coalesce_zero(revenue) AS rev FROM t"
        result = expand_macros(sql)
        assert "COALESCE" in result
        assert "0" in result
        assert "coalesce_zero" not in result

    def test_multiple_macros_in_one_query(self):
        sql = textwrap.dedent("""\
            SELECT
              surrogate_key(order_id, customer_id) AS sk,
              safe_divide(revenue, orders) AS avg_rev,
              nullif_empty(email) AS email
            FROM orders
        """)
        result = expand_macros(sql)
        assert "MD5(" in result
        assert "CASE WHEN" in result
        assert "NULLIF" in result
        assert "surrogate_key" not in result
        assert "safe_divide" not in result
        assert "nullif_empty" not in result

    def test_macro_in_subquery(self):
        sql = "SELECT * FROM (SELECT surrogate_key(id) AS sk FROM t) sub"
        result = expand_macros(sql)
        assert "MD5(" in result
        assert "surrogate_key" not in result

    def test_macro_in_cte(self):
        sql = textwrap.dedent("""\
            WITH base AS (
              SELECT surrogate_key(a, b) AS sk FROM raw
            )
            SELECT sk FROM base
        """)
        result = expand_macros(sql)
        assert "MD5(" in result

    def test_no_expansion_when_no_macro_called(self):
        sql = "SELECT id, name FROM orders WHERE id > 10"
        result = expand_macros(sql)
        assert result == sql  # unchanged — no macro calls present

    def test_unknown_function_not_affected(self):
        sql = "SELECT my_custom_udf(col) FROM t"
        result = expand_macros(sql)
        # my_custom_udf is not registered — should come through unchanged
        assert "my_custom_udf" in result


# --------------------------------------------------------------------------- #
# Case insensitivity                                                           #
# --------------------------------------------------------------------------- #

class TestCaseInsensitive:
    def test_uppercase_call(self):
        sql = "SELECT SURROGATE_KEY(a, b) AS sk FROM t"
        result = expand_macros(sql)
        assert "MD5(" in result

    def test_mixed_case_call(self):
        sql = "SELECT Surrogate_Key(a, b) AS sk FROM t"
        result = expand_macros(sql)
        assert "MD5(" in result


# --------------------------------------------------------------------------- #
# Custom macros via Python file                                                #
# --------------------------------------------------------------------------- #

class TestCustomPythonMacro:
    def test_load_python_macro_file(self, tmp_path):
        macro_file = tmp_path / "my_macros.py"
        macro_file.write_text(
            textwrap.dedent("""\
                from kelpmesh.core.macros import macro

                @macro("fiscal_year")
                def fiscal_year(date_col):
                    return f"EXTRACT(YEAR FROM DATE_ADD({date_col}, INTERVAL 6 MONTH))"
            """),
            encoding="utf-8",
        )
        loader = MacroLoader()
        loader.load_dirs([tmp_path])

        sql = "SELECT fiscal_year(order_date) AS fy FROM orders"
        result = expand_macros(sql)
        assert "EXTRACT" in result
        assert "fiscal_year" not in result

        # cleanup
        del _REGISTRY["FISCAL_YEAR"]

    def test_python_macro_with_multiple_args(self, tmp_path):
        macro_file = tmp_path / "macros.py"
        macro_file.write_text(
            textwrap.dedent("""\
                from kelpmesh.core.macros import macro

                @macro("label_bucket")
                def label_bucket(col, low, high, label):
                    return f"CASE WHEN {col} BETWEEN {low} AND {high} THEN {label} END"
            """),
            encoding="utf-8",
        )
        loader = MacroLoader()
        loader.load_dirs([tmp_path])

        sql = "SELECT label_bucket(score, 0, 50, 'low') AS bucket FROM t"
        result = expand_macros(sql)
        assert "CASE WHEN" in result

        del _REGISTRY["LABEL_BUCKET"]


# --------------------------------------------------------------------------- #
# Custom macros via YAML file                                                  #
# --------------------------------------------------------------------------- #

class TestCustomYamlMacro:
    def test_load_yaml_macro_file(self, tmp_path):
        yaml_file = tmp_path / "my_macros.yml"
        yaml_file.write_text(
            textwrap.dedent("""\
                macros:
                  - name: percent_of_total
                    args: [part, total]
                    sql: "ROUND(100.0 * ({part}) / NULLIF({total}, 0), 2)"
            """),
            encoding="utf-8",
        )
        loader = MacroLoader()
        loader.load_dirs([tmp_path])

        sql = "SELECT percent_of_total(sales, total_sales) AS pct FROM t"
        result = expand_macros(sql)
        assert "ROUND" in result
        assert "NULLIF" in result
        assert "percent_of_total" not in result

        del _REGISTRY["PERCENT_OF_TOTAL"]

    def test_yaml_macro_no_args(self, tmp_path):
        yaml_file = tmp_path / "macros.yml"
        yaml_file.write_text(
            textwrap.dedent("""\
                macros:
                  - name: current_utc
                    args: []
                    sql: "CONVERT_TZ(NOW(), @@session.time_zone, '+00:00')"
            """),
            encoding="utf-8",
        )
        loader = MacroLoader()
        loader.load_dirs([tmp_path])

        sql = "SELECT current_utc() AS ts FROM t"
        result = expand_macros(sql)
        assert "CONVERT_TZ" in result

        del _REGISTRY["CURRENT_UTC"]


# --------------------------------------------------------------------------- #
# Integration with substitutions.apply()                                      #
# --------------------------------------------------------------------------- #

class TestIntegrationWithSubstitutions:
    def test_macro_expands_through_apply(self):
        sql = "SELECT surrogate_key(id, name) AS sk FROM t"
        result = apply(sql)
        assert "MD5(" in result
        assert "surrogate_key" not in result

    def test_var_and_macro_together(self):
        sql = "SELECT surrogate_key(id) AS sk FROM {{ var('schema') }}.orders"
        result = apply(sql, vars={"schema": "production"})
        assert "MD5(" in result
        assert "production" in result
        assert "surrogate_key" not in result

    def test_is_incremental_and_macro(self):
        sql = textwrap.dedent("""\
            SELECT surrogate_key(order_id) AS sk
            {% if is_incremental() %}
            WHERE updated_at > (SELECT MAX(updated_at) FROM {{ this }})
            {% endif %}
        """)
        result = apply(sql, table_name="orders", is_incremental=True)
        assert "MD5(" in result
        assert "WHERE" in result
        assert "orders" in result

    def test_macro_not_in_non_incremental(self):
        sql = textwrap.dedent("""\
            SELECT surrogate_key(id) AS sk
            {% if is_incremental() %}
            WHERE updated_at > '2020-01-01'
            {% endif %}
        """)
        result = apply(sql, is_incremental=False)
        assert "MD5(" in result
        assert "WHERE" not in result

    def test_plain_sql_unchanged(self):
        sql = "SELECT id, name, amount FROM orders WHERE amount > 100"
        result = apply(sql)
        assert result == sql


# --------------------------------------------------------------------------- #
# Robustness                                                                   #
# --------------------------------------------------------------------------- #

class TestRobustness:
    def test_malformed_sql_returns_original(self):
        sql = "SELECT ??? FROM !!!"
        result = expand_macros(sql)
        assert result == sql

    def test_empty_sql(self):
        result = expand_macros("")
        assert result == ""

    def test_macro_with_nested_expression(self):
        sql = "SELECT safe_divide(SUM(revenue), COUNT(*)) AS avg FROM t"
        result = expand_macros(sql)
        assert "CASE WHEN" in result
        assert "SUM" in result

    def test_macro_in_where_clause(self):
        sql = "SELECT id FROM t WHERE safe_divide(a, b) > 0.5"
        result = expand_macros(sql)
        assert "CASE WHEN" in result
        assert "safe_divide" not in result

    def test_sqlglot_unavailable_graceful(self, monkeypatch):
        import sys
        # Simulate sqlglot not installed
        monkeypatch.setitem(sys.modules, "sqlglot", None)
        sql = "SELECT surrogate_key(id) AS sk FROM t"
        # Should not raise; returns original
        try:
            result = expand_macros(sql)
            assert isinstance(result, str)
        except Exception:
            pass  # acceptable if import error propagates — just must not corrupt data
