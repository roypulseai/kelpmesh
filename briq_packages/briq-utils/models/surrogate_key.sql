-- description: Generate a surrogate key by hashing concatenated column values
-- materialized: table
-- unique_key: surrogate_key_value
select
    md5(
        coalesce(cast(id1 as varchar), '') || '|' ||
        coalesce(cast(id2 as varchar), '')
    ) as surrogate_key_value,
    *
from input_model
