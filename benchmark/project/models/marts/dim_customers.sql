select
    c.customer_key,
    c.customer_name,
    c.market_segment,
    c.account_balance,
    c.nation_name,
    c.region_name,
    coalesce(f.order_count, 0) as order_count,
    f.lifetime_value,
    f.avg_order_value,
    f.first_order_date,
    f.last_order_date,
    f.days_since_last_order
from {{ ref('stg_customers') }} c
left join {{ ref('customer_features') }} f on f.customer_key = c.customer_key
