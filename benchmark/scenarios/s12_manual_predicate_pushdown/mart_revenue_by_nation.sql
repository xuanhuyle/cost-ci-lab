select
    c.nation_name,
    c.region_name,
    {{ dbt.date_trunc('month', 'ol.ship_date') }} as ship_month,
    count(distinct ol.order_key)                    as order_count,
    sum(ol.net_revenue)                             as net_revenue
from {{ ref('int_order_lines') }} ol
join {{ ref('dim_customers') }} c on c.customer_key = ol.customer_key
where ol.ship_date >= {{ dbt.date_trunc('month', run_date_minus(3, 'month')) }}
group by 1, 2, 3
