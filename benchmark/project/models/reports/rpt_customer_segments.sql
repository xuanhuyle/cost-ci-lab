select
    market_segment,
    nation_name,
    count(*)            as customer_count,
    avg(lifetime_value) as avg_lifetime_value,
    sum(order_count)    as order_count
from {{ ref('dim_customers') }}
group by 1, 2
