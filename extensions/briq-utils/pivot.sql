-- {{ materialized: ephemeral }}
-- Description: Pivot rows to columns using CASE/SUM aggregation pattern.
-- Usage: SELECT entity, SUM(CASE WHEN attr='val1' THEN 1 END) AS val1 FROM ...
-- Notes: Adapt the CASE expressions for your specific pivot columns.

SELECT 1 AS _dummy WHERE FALSE
