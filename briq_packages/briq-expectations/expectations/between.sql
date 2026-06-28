-- description: Assert that a column value is within a range
-- severity: error
select count(*) as failures
from {{ model }}
where {{ column }} < {{ min_value }}
   or {{ column }} > {{ max_value }}
