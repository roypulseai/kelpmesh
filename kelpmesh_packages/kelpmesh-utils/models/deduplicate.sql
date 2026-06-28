-- description: Deduplicate rows using row_number() over partition columns
with dedup as (
    select
        *,
        row_number() over (
            partition by partition_col
            order by order_col
        ) as _row_num
    from input_model
)
select * except (_row_num) from dedup where _row_num = 1
