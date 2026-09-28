select
    p.part_key,
    p.part_name,
    p.brand,
    p.part_type,
    count(*)              as supplier_count,
    min(ps.supply_cost)   as min_supply_cost,
    avg(ps.supply_cost)   as avg_supply_cost,
    sum(ps.available_qty) as total_available_qty
from {{ ref('stg_partsupp') }} ps
join {{ ref('stg_parts') }} p on p.part_key = ps.part_key
group by p.part_key, p.part_name, p.brand, p.part_type
