with orders as (
    select customer_key, order_key, order_date, total_price
    from {{ ref('stg_orders') }}
    where order_date <= {{ run_date() }}
)
select
    customer_key,
    count(*)         as order_count,
    sum(total_price) as lifetime_value,
    avg(total_price) as avg_order_value,
    min(order_date)  as first_order_date,
    max(order_date)  as last_order_date,
    {{ dbt.datediff('max(order_date)', run_date(), 'day') }} as days_since_last_order
from orders
group by customer_key
