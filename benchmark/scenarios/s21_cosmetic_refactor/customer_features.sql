-- Customer-level order features.
-- Grain: one row per customer with at least one order up to run_date.
with customer_orders as (

    select
        customer_key,
        order_key,
        order_date,
        total_price
    from {{ ref('stg_orders') }}
    where order_date <= {{ run_date() }}

)

select
    customer_key,
    count(*)            as order_count,       -- all orders, any status
    sum(total_price)    as lifetime_value,
    avg(total_price)    as avg_order_value,
    min(order_date)     as first_order_date,
    max(order_date)     as last_order_date,
    {{ dbt.datediff('max(order_date)', run_date(), 'day') }} as days_since_last_order
from customer_orders
group by customer_key
