select
    p_partkey     as part_key,
    p_name        as part_name,
    p_brand       as brand,
    p_type        as part_type,
    p_size        as part_size,
    p_retailprice as retail_price
from {{ source('tpch', 'part') }}
