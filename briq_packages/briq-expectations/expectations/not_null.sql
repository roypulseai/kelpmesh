-- description: Assert that a column has no null values
-- severity: error
select count(*) as failures
from {{ model }}
where {{ column }} is null
