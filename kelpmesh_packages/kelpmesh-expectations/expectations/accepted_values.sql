-- description: Assert that a column only contains accepted values
-- severity: warn
select count(*) as failures
from {{ model }}
where {{ column }} not in ({{ values }})
