select
    ol.part_key,
    pc.part_name,
    pc.brand,
    sum(ol.quantity)                                            as quantity_sold,
    sum(ol.net_revenue)                                         as net_revenue,
    sum(ol.net_revenue) - sum(ol.quantity * pc.min_supply_cost) as est_margin,
    avg(ps.supply_cost)                                         as avg_supplier_cost
from {{ ref('int_order_lines') }} ol
join {{ ref('part_supplier_costs') }} pc on pc.part_key = ol.part_key
join {{ ref('stg_partsupp') }} ps on ps.part_key = ol.part_key
group by ol.part_key, pc.part_name, pc.brand
