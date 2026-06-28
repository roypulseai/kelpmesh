-- {{ materialized: ephemeral }}
-- Description: Expect a column to have no NULL values.
-- Usage: SELECT * FROM expect_column_not_null WHERE ...

SELECT COUNT(*) AS failures
FROM table_name
WHERE column_name IS NULL
