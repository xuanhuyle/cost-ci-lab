with orders as (
    select customer_key, order_key, order_date, total_price
    from {{ ref('stg_orders') }}
    where order_date <= {{ run_date() }}
),
sequenced as (
    select
        orders.*,
        lag(order_date) over (partition by customer_key order by order_date, order_key) as previous_order_date,
        sum(total_price) over (partition by customer_key order by order_date, order_key
                               rows between unbounded preceding and current row)    as running_value,
        percent_rank() over (partition by customer_key order by total_price)        as value_percentile
    from orders
)
select
    customer_key,
    count(*)         as order_count,
    sum(total_price) as lifetime_value,
    avg(total_price) as avg_order_value,
    min(order_date)  as first_order_date,
    max(order_date)  as last_order_date,
    {{ dbt.datediff('max(order_date)', run_date(), 'day') }} as days_since_last_order,
    avg({{ dbt.datediff('previous_order_date', 'order_date', 'day') }}) as avg_days_between_orders,
    max(running_value) as max_running_value,
    avg(value_percentile) as avg_value_percentile
from sequenced
group by customer_key
