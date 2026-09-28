with order_counts as (
    select customer_key, count(*) as order_count
    from {{ ref('stg_orders') }}
    where order_date <= {{ run_date() }}
    group by customer_key
),
order_values as (
    select customer_key, sum(total_price) as lifetime_value, avg(total_price) as avg_order_value
    from {{ ref('stg_orders') }}
    where order_date <= {{ run_date() }}
    group by customer_key
),
order_recency as (
    select customer_key, min(order_date) as first_order_date, max(order_date) as last_order_date
    from {{ ref('stg_orders') }}
    where order_date <= {{ run_date() }}
    group by customer_key
)
select
    c.customer_key,
    c.order_count,
    v.lifetime_value,
    v.avg_order_value,
    r.first_order_date,
    r.last_order_date,
    {{ dbt.datediff('r.last_order_date', run_date(), 'day') }} as days_since_last_order
from order_counts c
join order_values v on v.customer_key = c.customer_key
join order_recency r on r.customer_key = c.customer_key
