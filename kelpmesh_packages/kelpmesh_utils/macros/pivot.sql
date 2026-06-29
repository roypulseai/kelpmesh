-- ============================================================
-- pivot.sql
-- Pivot and unpivot macros for KelpMesh.
-- ============================================================

-- ── pivot ────────────────────────────────────────────────────
-- Pivot a long table to wide format.
--
-- Arguments:
--   relation        — source table / subquery
--   rows            — column(s) that form the row key (GROUP BY)
--   columns         — the column whose distinct values become new columns
--   agg             — aggregate function: SUM | COUNT | MAX | MIN | AVG
--   then_value      — value expression to aggregate (often the value column)
--   else_value      — fallback when no rows match (often 0 or NULL)
--
-- Example:
--   SELECT * FROM pivot(
--       'monthly_revenue',
--       'product_id',
--       'month',
--       'SUM',
--       'revenue',
--       '0'
--   )
--
-- NOTE: Because column names are data-driven, this macro
-- generates static CASE WHEN SQL. For truly dynamic pivots
-- you must know the column values ahead of time and list them
-- via get_column_values() first, then hand-code or template
-- the CASE expressions.
-- ============================================================

macros:
  - name: pivot
    args: [relation, rows, columns, agg, then_value, else_value]
    sql: >
      SELECT
          {rows},
          {agg}(CASE WHEN {columns} = '{{ value }}' THEN {then_value} ELSE {else_value} END) AS "{{ value }}"
          -- Repeat the line above for each distinct value of {columns}.
          -- Use get_column_values('{relation}', '{columns}', 200) to enumerate values.
      FROM {relation}
      GROUP BY {rows}

-- ── unpivot ──────────────────────────────────────────────────
-- Unpivot a wide table to long (EAV) format using UNPIVOT
-- syntax supported by DuckDB and Snowflake.
--
-- Arguments:
--   relation              — source table or subquery alias
--   cast_to               — target data type for value column (e.g. DOUBLE)
--   exclude               — comma-separated columns to keep as-is
--   field_name            — name of the new "attribute" column  (default: field_name)
--   value_name            — name of the new "value" column      (default: value)
--
-- Example:
--   SELECT * FROM unpivot(
--       'wide_metrics',
--       'DOUBLE',
--       'user_id, event_date',
--       'metric_name',
--       'metric_value'
--   )
  - name: unpivot
    args: [relation, cast_to, exclude, field_name, value_name]
    sql: >
      (
          SELECT {exclude}, {field_name}, CAST({value_name} AS {cast_to}) AS {value_name}
          FROM {relation}
          UNPIVOT (
              {value_name} FOR {field_name} IN (
                  -- list value columns here, e.g. jan, feb, mar
              )
          )
      )

-- ── unpivot_duckdb ───────────────────────────────────────────
-- DuckDB-native unpivot using UNPIVOT ALL COLUMNS syntax.
-- Automatically pivots every column not in the EXCLUDE list.
-- Arguments:
--   relation  — source table / subquery alias
--   exclude   — columns to keep (identity columns)
--   field_name — label column name
--   value_name — value column name
  - name: unpivot_duckdb
    args: [relation, exclude, field_name, value_name]
    sql: >
      (
          UNPIVOT {relation}
          ON COLUMNS(* EXCLUDE ({exclude}))
          INTO NAME {field_name} VALUE {value_name}
      )
