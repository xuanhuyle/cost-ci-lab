| scenario | files changed | dbt state:modified | rendered-SQL diff | missed by dbt | flagged, render-identical | modified+ | consumers |
|---|---|---|---|---|---|---|---|
| s01_widen_date_filter |  | int_order_lines | int_order_lines | - | - | 3 | bi_nation_trend |
| s02_remove_partition_pruning |  | int_order_lines | int_order_lines | - | - | 3 | bi_nation_trend |
| s03_expand_incremental_window |  | fct_daily_revenue | fct_daily_revenue | - | - | 2 | bi_kpi_tiles |
| s04_incremental_to_table |  | fct_daily_revenue | fct_daily_revenue | - | - | 2 | bi_kpi_tiles |
| s05_many_to_many_join |  | mart_part_profitability | mart_part_profitability | - | - | 1 | - |
| s06_superlinear_self_join |  | mart_part_profitability | mart_part_profitability | - | - | 1 | - |
| s07_unnecessary_distinct |  | int_order_lines | int_order_lines | - | - | 3 | bi_nation_trend |
| s08_expensive_window |  | customer_features | customer_features | - | - | 4 | bi_customer_lookup, bi_segments_dashboard, bi_nation_trend |
| s09_repeated_scans |  | customer_features | customer_features | - | - | 4 | bi_customer_lookup, bi_segments_dashboard, bi_nation_trend |
| s10_table_to_view |  | dim_customers | dim_customers | - | - | 3 | bi_customer_lookup, bi_segments_dashboard, bi_nation_trend |
| s11_view_to_table |  | rpt_customer_segments | rpt_customer_segments | - | - | 1 | bi_segments_dashboard |
| s12_manual_predicate_pushdown |  | mart_revenue_by_nation | mart_revenue_by_nation | - | - | 1 | bi_nation_trend |
| s13_select_fewer_columns |  | int_order_lines | int_order_lines | - | - | 3 | bi_nation_trend |
| s14_join_preaggregation |  | customer_ltv_monthly | customer_ltv_monthly | - | - | 1 | - |
| s15_include_returns |  | int_order_lines | int_order_lines | - | - | 3 | bi_nation_trend |
| s16_new_model |  | mart_customer_churn | mart_customer_churn | - | - | 1 | - |
| s17_monthly_job_regression |  | customer_ltv_monthly | customer_ltv_monthly | - | - | 1 | - |
| s18_frequent_cheap_view |  | rpt_daily_kpis | rpt_daily_kpis | - | - | 1 | bi_kpi_tiles |
| s19_idle_capacity_absorbs |  | rpt_daily_kpis | rpt_daily_kpis | - | - | 1 | bi_kpi_tiles |
| s20_bytes_up_capacity_pricing |  | int_order_lines | int_order_lines | - | - | 3 | bi_nation_trend |
| s21_cosmetic_refactor |  | customer_features | customer_features | - | - | 4 | bi_customer_lookup, bi_segments_dashboard, bi_nation_trend |
| s22_sort_for_determinism |  | int_order_lines | int_order_lines | - | - | 3 | bi_nation_trend |
| s23_macro_change |  | customer_ltv_monthly, fct_daily_revenue, int_order_lines | customer_ltv_monthly, fct_daily_revenue, int_order_lines | - | - | 6 | bi_kpi_tiles, bi_nation_trend |
| s24_var_default_change |  | - | fct_daily_revenue | fct_daily_revenue | - | 0 | - |
| s25_config_inheritance |  | stg_customers, stg_lineitem, stg_orders, stg_parts, stg_partsupp | stg_customers, stg_lineitem, stg_orders, stg_parts, stg_partsupp | - | - | 15 | bi_customer_lookup, bi_segments_dashboard, bi_kpi_tiles, bi_nation_trend |
| s26_include_future_shipments |  | int_order_lines | int_order_lines | - | - | 3 | bi_nation_trend |
