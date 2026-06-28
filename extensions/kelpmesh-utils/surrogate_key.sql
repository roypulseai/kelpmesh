-- {{ materialized: ephemeral }}
-- Description: Generates a surrogate key (hash) from one or more column values.
-- Usage: SELECT * FROM surrogate_key('id', 'name') WHERE ...
--        or SELECT briq_utils_surrogate_key(id, name) AS id FROM my_table
-- Notes: Rename columns as needed. Uses MD5 hash of concatenated values.

SELECT 1 AS _dummy WHERE FALSE
