{{ config(tags=['monthly']) }}

with lines as (
    select
        o.customer_key,
        o.order_key,
        o.order_date,
        {{ net_revenue('l.extended_price', 'l.discount') }} as revenue
    from {{ ref('stg_orders') }} o
    join {{ ref('stg_lineitem') }} l on l.order_key = o.order_key
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
