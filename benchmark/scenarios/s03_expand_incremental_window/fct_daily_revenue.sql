{{ config(materialized='incremental', unique_key='ship_date', incremental_strategy='delete+insert') }}

select
    l.ship_date,
    count(*)                                                 as line_count,
    sum(l.quantity)                                          as total_quantity,
    sum({{ net_revenue('l.extended_price', 'l.discount') }}) as net_revenue,
    sum(case when l.return_flag = 'R'
             then {{ net_revenue('l.extended_price', 'l.discount') }}
             else 0 end)                                     as returned_revenue
from {{ ref('stg_lineitem') }} l
where l.ship_date <= {{ run_date() }}
{% if is_incremental() %}
  and l.ship_date > {{ run_date_minus(45) }}
{% endif %}
group by l.ship_date
