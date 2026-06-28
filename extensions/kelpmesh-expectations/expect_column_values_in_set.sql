-- {{ materialized: ephemeral }}
-- Description: Expect column values to be within an accepted set.
-- Usage: SELECT * FROM expect_column_values_in_set WHERE ...
-- Note: Replace 'val1', 'val2' with your accepted values.

SELECT COUNT(*) AS failures
FROM table_name
WHERE column_name NOT IN ('val1', 'val2')
