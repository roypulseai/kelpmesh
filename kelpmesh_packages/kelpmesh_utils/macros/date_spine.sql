-- ============================================================
-- date_spine.sql
-- Date spine generation macro for KelpMesh.
-- Generates a complete, gap-free sequence of dates between
-- start_date and end_date at the specified granularity.
-- ============================================================

-- ── date_spine ───────────────────────────────────────────────
-- Generate a complete date spine from start_date to end_date.
--
-- Arguments:
--   start_date  — inclusive start, e.g. '2020-01-01'
--   end_date    — inclusive end, e.g. CURRENT_DATE
--   datepart    — 'day' (default) | 'week' | 'month' | 'quarter' | 'year'
--
-- Returns a single-column result: date_day DATE
--
-- Usage — embed as a CTE:
--   WITH spine AS (
--       SELECT date_day FROM date_spine('2023-01-01', CURRENT_DATE, 'day')
--   )
--   SELECT spine.date_day, COALESCE(SUM(o.amount), 0) AS revenue
--   FROM spine
--   LEFT JOIN orders o ON o.order_date = spine.date_day
--   GROUP BY 1
--   ORDER BY 1
-- ============================================================

-- DuckDB / standard SQL implementation using generate_series
-- The INTERVAL syntax used here is ANSI SQL compatible.
-- For warehouses that don't support generate_series, see the
-- recursive CTE fallback below.

macros:
  - name: date_spine
    args: [start_date, end_date, datepart]
    sql: >
      (
          SELECT
              CAST(
                  CASE '{datepart}'
                      WHEN 'day'     THEN gs.n::DATE
                      WHEN 'week'    THEN DATE_TRUNC('week',  gs.n::DATE)
                      WHEN 'month'   THEN DATE_TRUNC('month', gs.n::DATE)
                      WHEN 'quarter' THEN DATE_TRUNC('quarter', gs.n::DATE)
                      WHEN 'year'    THEN DATE_TRUNC('year',  gs.n::DATE)
                      ELSE gs.n::DATE
                  END AS DATE
              ) AS date_day
          FROM (
              SELECT UNNEST(
                  GENERATE_SERIES(
                      {start_date}::DATE,
                      {end_date}::DATE,
                      INTERVAL 1 DAY
                  )
              ) AS n
          ) gs
          GROUP BY 1
          ORDER BY 1
      )

-- ── date_spine_recursive (fallback for non-DuckDB) ───────────
-- Recursive CTE version for warehouses without generate_series.
-- Warehouses: Snowflake, Redshift, Postgres.
-- Usage: same as date_spine but invoke as date_spine_recursive(...)
  - name: date_spine_recursive
    args: [start_date, end_date]
    sql: >
      (
          WITH RECURSIVE date_series AS (
              SELECT CAST({start_date} AS DATE) AS date_day
              UNION ALL
              SELECT date_day + INTERVAL '1 DAY'
              FROM date_series
              WHERE date_day < CAST({end_date} AS DATE)
          )
          SELECT date_day FROM date_series ORDER BY date_day
      )
