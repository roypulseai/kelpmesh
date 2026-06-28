-- description: Assert that a column has unique values
-- severity: error
select count(*) as failures
from (
    select {{ column }}
    from {{ model }}
    group by {{ column }}
    having count(*) > 1
) t
