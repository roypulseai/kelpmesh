-- description: Generate a date spine from 2020-01-01 to 2030-12-31
with date_spine as (
    select
        cast('2020-01-01' as date) + interval (value) day as date_day
    from generate_series(0, 4017) as t(value)
)
select
    date_day,
    extract(year from date_day) as year,
    extract(month from date_day) as month,
    extract(day from date_day) as day,
    extract(quarter from date_day) as quarter,
    dayname(date_day) as day_name,
    monthname(date_day) as month_name,
    case when dayname(date_day) in ('Saturday', 'Sunday') then 1 else 0 end as is_weekend
from date_spine
