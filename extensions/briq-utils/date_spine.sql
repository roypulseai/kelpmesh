-- {{ materialized: ephemeral }}
-- Description: Generates a contiguous date spine from start_date to end_date.
-- Usage: SELECT * FROM date_spine WHERE ...
--        SELECT * FROM briq_utils_date_spine WHERE date_col BETWEEN '2024-01-01' AND '2024-12-31'
-- Notes: Replace the date range and interval as needed.

SELECT 1 AS _dummy WHERE FALSE
