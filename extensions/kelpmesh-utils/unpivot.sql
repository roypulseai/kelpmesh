-- {{ materialized: ephemeral }}
-- Description: Unpivot/reshape columns into key-value pairs using UNION ALL.
-- Usage: SELECT entity, 'col1' AS attr, col1 AS value FROM my_table
--        UNION ALL
--        SELECT entity, 'col2' AS attr, col2 AS value FROM my_table

SELECT 1 AS _dummy WHERE FALSE
