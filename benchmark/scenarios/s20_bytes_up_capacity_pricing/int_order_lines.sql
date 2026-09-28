select
    l.order_key,
    l.line_number,
    l.part_key,
    l.supplier_key,
    o.customer_key,
    o.order_date,
    o.order_priority,
    o.clerk,
    l.ship_date,
    l.commit_date,
    l.receipt_date,
    l.ship_mode,
    l.ship_instruct,
    l.return_flag,
    l.line_status,
    l.quantity,
    l.extended_price,
    l.discount,
    l.tax,
    {{ net_revenue('l.extended_price', 'l.discount') }} as net_revenue,
    l.line_comment,
    o.order_comment
from {{ ref('stg_lineitem') }} l
join {{ ref('stg_orders') }} o on o.order_key = l.order_key
where l.ship_date > {{ run_date_minus(var('order_lines_window_days')) }}
  and l.ship_date <= {{ run_date() }}
  and l.return_flag <> 'R'
