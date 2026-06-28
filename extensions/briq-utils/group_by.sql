-- {{ materialized: ephemeral }}
-- Description: Helper for dynamic GROUP BY operations. Provides a reusable
--              pattern for grouping by multiple columns with aggregations.
-- Usage: SELECT group_key, agg_val FROM (GROUP BY group_key)

SELECT 1 AS _dummy WHERE FALSE
