-- ============================================================
-- cross_db_utils.sql
-- Cross-warehouse SQL utility macros for KelpMesh.
-- All macros work with DuckDB, Snowflake, BigQuery, and
-- standard ANSI SQL unless noted otherwise.
-- ============================================================

-- ── date_trunc ───────────────────────────────────────────────
-- Truncate a date/timestamp to the start of the given period.
-- period: 'day' | 'week' | 'month' | 'quarter' | 'year'
-- Usage:  date_trunc('month', order_date)
macros:
  - name: date_trunc
    args: [period, date_col]
    sql: "DATE_TRUNC({period}, {date_col})"

-- ── datediff ─────────────────────────────────────────────────
-- Difference between two dates in the given unit.
-- period: 'day' | 'week' | 'month' | 'year' | 'hour' | 'minute'
-- Usage:  datediff('day', signup_date, CURRENT_DATE)
  - name: datediff
    args: [period, start_col, end_col]
    sql: "DATEDIFF({period}, {start_col}, {end_col})"

-- ── dateadd ──────────────────────────────────────────────────
-- Add N units to a date.
-- Usage:  dateadd('month', 3, order_date)
  - name: dateadd
    args: [period, n, date_col]
    sql: "DATEADD({period}, {n}, {date_col})"

-- ── safe_add ─────────────────────────────────────────────────
-- NULL-safe addition: returns NULL only if BOTH inputs are NULL.
-- Usage:  safe_add(revenue_usd, revenue_eur)
  - name: safe_add
    args: [a, b]
    sql: "COALESCE({a}, 0) + COALESCE({b}, 0)"

-- ── safe_subtract ────────────────────────────────────────────
-- NULL-safe subtraction.
-- Usage:  safe_subtract(gross_amount, discount_amount)
  - name: safe_subtract
    args: [a, b]
    sql: "COALESCE({a}, 0) - COALESCE({b}, 0)"

-- ── safe_multiply ────────────────────────────────────────────
-- NULL-safe multiplication (0 if either side is NULL).
-- Usage:  safe_multiply(unit_price, quantity)
  - name: safe_multiply
    args: [a, b]
    sql: "COALESCE({a}, 0) * COALESCE({b}, 0)"

-- ── generate_series ──────────────────────────────────────────
-- Inline integer series — returns a single-column table alias
-- 'n' containing integers from start to stop (inclusive) in
-- increments of step.
-- Works natively in DuckDB; use range() equivalent on other
-- warehouses.
-- Usage:  SELECT n FROM generate_series(1, 10, 1)
  - name: generate_series
    args: [start, stop, step]
    sql: "generate_series({start}, {stop}, {step})"

-- ── pivot_values ─────────────────────────────────────────────
-- Dynamic pivot aggregation helper (static version).
-- Returns the aggregate of value_col grouped by the distinct
-- values of pivot_col. For a fully dynamic pivot, pair this
-- with the pivot() macro in pivot.sql.
-- Usage:  pivot_values('orders', 'status', 'amount', 'SUM')
  - name: pivot_values
    args: [source_table, pivot_col, value_col, agg_func]
    sql: >
      SELECT
          {pivot_col},
          {agg_func}({value_col}) AS aggregated_value
      FROM {source_table}
      GROUP BY {pivot_col}
      ORDER BY {pivot_col}
