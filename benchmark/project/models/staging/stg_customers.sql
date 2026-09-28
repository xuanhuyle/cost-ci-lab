select
    c.c_custkey    as customer_key,
    c.c_name       as customer_name,
    c.c_mktsegment as market_segment,
    c.c_acctbal    as account_balance,
    n.n_name       as nation_name,
    r.r_name       as region_name
from {{ source('tpch', 'customer') }} c
join {{ source('tpch', 'nation') }} n on n.n_nationkey = c.c_nationkey
join {{ source('tpch', 'region') }} r on r.r_regionkey = n.n_regionkey
