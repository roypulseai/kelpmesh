-- {{ materialized: ephemeral }}
-- Description: Expect all values in a column to be unique.
-- Usage: SELECT * FROM expect_column_unique WHERE ...
-- Note: Replace table_name and column_name in your actual test.

SELECT COUNT(*) AS failures
FROM (
    SELECT column_name FROM table_name
    GROUP BY column_name HAVING COUNT(*) > 1
) _dup
