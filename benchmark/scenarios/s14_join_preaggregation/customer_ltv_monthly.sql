{{ config(tags=['monthly']) }}

with order_revenue as (
    -- aggregate lines to one row per order before joining
    select order_key, sum({{ net_revenue('extended_price', 'discount') }}) as revenue
    from {{ ref('stg_lineitem') }}
    group by order_key
),
lines as (
    select o.customer_key, o.order_key, o.order_date, r.revenue
    from {{ ref('stg_orders') }} o
    join order_revenue r on r.order_key = o.order_key
    where o.order_date <= {{ run_date() }}
),
monthly as (
    select
        customer_key,
        {{ dbt.date_trunc('month', 'order_date') }} as order_month,
        sum(revenue)              as revenue,
        count(distinct order_key) as order_count
    from lines
    group by 1, 2
)
select
    customer_key,
    order_month,
    revenue,
    order_count,
    sum(revenue) over (partition by customer_key order by order_month
                       rows between unbounded preceding and current row) as cumulative_revenue,
    min(order_month) over (partition by customer_key)                     as cohort_month
from monthly
