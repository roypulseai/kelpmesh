-- {{ materialized: ephemeral }}
-- Description: Expect row count to match between two tables.
-- Usage: SELECT * FROM expect_rowcount_equal WHERE ...
-- Note: Replace table_a and table_b with actual table names.

SELECT
    (SELECT COUNT(*) FROM table_a) AS count_a,
    (SELECT COUNT(*) FROM table_b) AS count_b,
    CASE WHEN (SELECT COUNT(*) FROM table_a) = (SELECT COUNT(*) FROM table_b)
         THEN 0 ELSE 1 END AS failures
