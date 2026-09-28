select
    ship_date,
    net_revenue,
    returned_revenue,
    line_count,
    avg(net_revenue) over (order by ship_date rows between 6 preceding and current row) as net_revenue_7d_avg
from {{ ref('fct_daily_revenue') }}
where ship_date > {{ run_date_minus(30) }}
