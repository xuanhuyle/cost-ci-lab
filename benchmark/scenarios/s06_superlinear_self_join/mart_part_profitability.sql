with peer_volume as (
    -- how busy was the ship mode on the day each line shipped
    select a.order_key, a.line_number, count(*) as same_day_mode_lines
    from {{ ref('int_order_lines') }} a
    join {{ ref('int_order_lines') }} b
      on b.ship_date = a.ship_date and b.ship_mode = a.ship_mode
    group by a.order_key, a.line_number
)
select
    ol.part_key,
    pc.part_name,
    pc.brand,
    sum(ol.quantity)                                            as quantity_sold,
    sum(ol.net_revenue)                                         as net_revenue,
    sum(ol.net_revenue) - sum(ol.quantity * pc.min_supply_cost) as est_margin,
    avg(pv.same_day_mode_lines)                                 as avg_same_day_mode_lines
from {{ ref('int_order_lines') }} ol
join {{ ref('part_supplier_costs') }} pc on pc.part_key = ol.part_key
join peer_volume pv on pv.order_key = ol.order_key and pv.line_number = ol.line_number
group by ol.part_key, pc.part_name, pc.brand
