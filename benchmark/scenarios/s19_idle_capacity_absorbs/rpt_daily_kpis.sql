select
    cur.ship_date,
    cur.net_revenue,
    cur.returned_revenue,
    cur.line_count,
    avg(cur.net_revenue) over (order by cur.ship_date rows between 6 preceding and current row)  as net_revenue_7d_avg,
    avg(cur.net_revenue) over (order by cur.ship_date rows between 27 preceding and current row) as net_revenue_28d_avg,
    prev.net_revenue                                                                            as net_revenue_last_year
from {{ ref('fct_daily_revenue') }} cur
left join {{ ref('fct_daily_revenue') }} prev
  on prev.ship_date = cast({{ dbt.dateadd('day', -364, 'cur.ship_date') }} as date)
where cur.ship_date > {{ run_date_minus(30) }}
