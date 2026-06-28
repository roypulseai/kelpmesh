-- description: Hash all columns into a single fingerprint column
-- materialized: table
with hashed as (
    select
        *,
        md5(
            coalesce(cast(col1 as varchar), '') || '|' ||
            coalesce(cast(col2 as varchar), '')
        ) as row_hash
    from input_model
)
select * from hashed
