-- description: Generate a sequence of numbers from 1 to 10000
with generate_series as (
    select * from generate_series(1, 10000) as t(value)
)
select * from generate_series
