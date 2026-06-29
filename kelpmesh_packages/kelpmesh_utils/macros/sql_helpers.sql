-- ============================================================
-- sql_helpers.sql
-- SQL construction helper macros for KelpMesh.
-- ============================================================

-- ── star ─────────────────────────────────────────────────────
-- Generate a SELECT list for all columns in a relation,
-- optionally excluding specified columns.
-- Usage:  SELECT star('orders', ['updated_at', '_fivetran_synced'])
--
-- Implemented as a Python macro (see macros/sql_helpers.py).
-- The SQL template below is a fallback that selects all columns.
macros:
  - name: star
    args: [relation]
    sql: "{relation}.*"

-- ── union_relations ──────────────────────────────────────────
-- UNION ALL two tables, aligning columns by name.
-- Usage:  union_relations('stg_orders_us', 'stg_orders_eu')
  - name: union_relations
    args: [relation_a, relation_b]
    sql: >
      SELECT * FROM {relation_a}
      UNION ALL
      SELECT * FROM {relation_b}

-- ── get_column_values ────────────────────────────────────────
-- Return up to max_records distinct non-null values from a
-- column as a subquery, useful for dynamic IN lists.
-- Usage:  SELECT * FROM orders WHERE status IN (get_column_values('orders', 'status', 50))
  - name: get_column_values
    args: [table, column, max_records]
    sql: >
      (
          SELECT DISTINCT {column}
          FROM {table}
          WHERE {column} IS NOT NULL
          LIMIT {max_records}
      )

-- ── deduplicate ──────────────────────────────────────────────
-- Return deduplicated rows using ROW_NUMBER() OVER PARTITION.
-- Keep the first row per partition_by, ordered by order_by.
-- Usage:  SELECT * FROM deduplicate('raw_events', 'event_id', 'received_at DESC')
  - name: deduplicate
    args: [relation, partition_by, order_by]
    sql: >
      (
          SELECT *
          FROM (
              SELECT
                  *,
                  ROW_NUMBER() OVER (
                      PARTITION BY {partition_by}
                      ORDER BY {order_by}
                  ) AS _row_num
              FROM {relation}
          ) AS _dedup
          WHERE _row_num = 1
      )

-- ── surrogate_key ────────────────────────────────────────────
-- MD5 hash of one or more fields joined with '-'.
-- Fields are cast to VARCHAR and NULLs replaced with empty string.
-- Usage:  surrogate_key(order_id, line_item_id)
  - name: surrogate_key
    args: [field_a, field_b]
    sql: >
      MD5(
          COALESCE(CAST({field_a} AS VARCHAR), '')
          || '-' ||
          COALESCE(CAST({field_b} AS VARCHAR), '')
      )

-- ── generate_surrogate_key ───────────────────────────────────
-- Alias for surrogate_key — dbt-utils compatibility.
-- Usage:  generate_surrogate_key(order_id, line_item_id)
  - name: generate_surrogate_key
    args: [field_a, field_b]
    sql: >
      MD5(
          COALESCE(CAST({field_a} AS VARCHAR), '')
          || '-' ||
          COALESCE(CAST({field_b} AS VARCHAR), '')
      )

-- ── safe_divide ──────────────────────────────────────────────
-- Division that returns a default value instead of erroring
-- on zero or NULL denominators.
-- Usage:  safe_divide(revenue, order_count, 0)
  - name: safe_divide
    args: [numerator, denominator, default_val]
    sql: >
      CASE
          WHEN ({denominator}) IS NULL OR ({denominator}) = 0
          THEN {default_val}
          ELSE ({numerator}) / ({denominator})
      END
