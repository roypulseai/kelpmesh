-- description: Assert that row count is between min and max
-- severity: error
with counts as (
    select count(*) as cnt
    from {{ model }}
)
select count(*) as failures
from counts
where cnt < {{ min_count }} or cnt > {{ max_count }}
