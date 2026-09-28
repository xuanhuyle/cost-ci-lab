with customer_months as (
    select
        ol.customer_key,
        {{ dbt.date_trunc('month', 'ol.order_date') }} as order_month,
        sum(ol.net_revenue) as revenue
    from {{ ref('int_order_lines') }} ol
    group by 1, 2
),
sequenced as (
    select
        cm.*,
        lag(order_month) over (partition by customer_key order by order_month) as previous_month,
        avg(revenue) over (partition by customer_key order by order_month
                           rows between 2 preceding and current row)          as revenue_3m_avg
    from customer_months cm
)
select
    s.customer_key,
    d.market_segment,
    d.nation_name,
    max(s.order_month)                                   as last_active_month,
    count(*)                                             as active_months,
    sum(case when s.previous_month is null then 1 else 0 end) as reactivations,
    avg(s.revenue_3m_avg)                                as avg_revenue_3m,
    max(d.days_since_last_order)                         as days_since_last_order
from sequenced s
join {{ ref('dim_customers') }} d on d.customer_key = s.customer_key
group by 1, 2, 3
