Monthly $ (SIMULATED; ASSUMED unit scaling κ=100). Cell = truth marginal / naive attributed.

| scenario | own_context | snowflake_dedicated | snowflake_always_on_bi | attributed_per_second | bigquery_on_demand | bigquery_editions | databricks_sql_serverless |
|---|---|---|---|---|---|---|---|
| s01_widen_date_filter | +90 / +90 | +90 / +90 | +90 / +90 | +90 / +90 | +10 / +10 | +62 / +34 | +126 / +126 |
| s02_remove_partition_pruning | +2 / +3 | +2 / +3 | +2 / +3 | +3 / +3 | +23 / +23 | +1 / -0 | +3 / +4 |
| s03_expand_incremental_window | +1 / +4 | +1 / +4 | +1 / +4 | +4 / +4 | +6 / +6 | +0 / +1 | +1 / +6 |
| s04_incremental_to_table | +47 / +49 | +47 / +49 | +47 / +49 | +49 / +49 | +282 / +282 | +38 / +25 | +66 / +69 |
| s05_many_to_many_join | +7 / +7 | +7 / +7 | +7 / +7 | +7 / +7 | +1 / +1 | +3 / +3 | +10 / +10 |
| s06_superlinear_self_join | +208 / +208 | +208 / +208 | +208 / +208 | +208 / +208 | +1 / +1 | +109 / +93 | +292 / +292 |
| s07_unnecessary_distinct | +3 / +2 | +3 / +2 | +3 / +2 | +2 / +2 | +0 / +0 | +1 / +3 | +4 / +3 |
| s08_expensive_window | +24 / +15 | +24 / +15 | +24 / +15 | +15 / +15 | +0 / +0 | +12 / +9 | +33 / +22 |
| s09_repeated_scans | +3 / +0 | +3 / +0 | +3 / +0 | +0 / +0 | +1 / +1 | -5 / +0 | +5 / +1 |
| s10_table_to_view | -11 / +57 | -11 / +57 | -11 / +57 | +57 / +57 | +166 / +166 | -9 / +14 | -15 / +79 |
| s11_view_to_table | +0 / -25 | +0 / -25 | +0 / -25 | -25 / -25 | -67 / -67 | +0 / -13 | +0 / -35 |
| s12_manual_predicate_pushdown | +0 / +0 | +0 / +0 | +0 / +0 | +0 / +0 | +0 / +0 | +0 / +0 | +0 / +0 |
| s13_select_fewer_columns | -30 / -30 | -30 / -30 | -30 / -30 | -30 / -30 | -3 / -3 | -7 / -3 | -42 / -42 |
| s14_join_preaggregation | -1 / -1 | -1 / -1 | -1 / -1 | -1 / -1 | +0 / +0 | -0 / -0 | -1 / -1 |
| s15_include_returns | -1 / -1 | -1 / -1 | -1 / -1 | -1 / -1 | +0 / +0 | -0 / +0 | -1 / -1 |
| s16_new_model | +7 / +7 | +7 / +7 | +7 / +7 | +7 / +7 | +1 / +1 | +1 / +2 | +10 / +10 |
| s17_monthly_job_regression | +1 / +1 | +1 / +1 | +1 / +1 | +1 / +1 | +0 / +0 | +1 / +1 | +2 / +2 |
| s18_frequent_cheap_view | -0 / +12 | -0 / +12 | -0 / +12 | +12 / +12 | +1 / +1 | +0 / +0 | -0 / +17 |
| s19_idle_capacity_absorbs | -0 / +17 | +0 / +17 | -0 / +17 | +17 / +17 | +1 / +1 | +0 / +1 | +0 / +23 |
| s20_bytes_up_capacity_pricing | +0 / +2 | +20 / +20 | +20 / +20 | +20 / +20 | +2 / +2 | +5 / +2 | +28 / +28 |
| s21_cosmetic_refactor | +0 / -0 | +0 / -0 | +0 / -0 | -0 / -0 | +0 / +0 | -0 / -1 | +0 / -1 |
| s22_sort_for_determinism | -24 / -24 | -24 / -24 | -24 / -24 | -24 / -24 | +0 / +0 | -4 / +1 | -33 / -33 |
| s23_macro_change | +0 / +1 | +0 / +1 | +0 / +1 | +1 / +1 | +0 / +0 | +0 / -0 | +1 / +2 |
| s24_var_default_change | +0 / +0 | +0 / +0 | +0 / +0 | +0 / +0 | +0 / +0 | +0 / +0 | +0 / +0 |
| s25_config_inheritance | +317 / +328 | +317 / +328 | +317 / +328 | +328 / +328 | +44 / +44 | +86 / +42 | +368 / +459 |
| s26_include_future_shipments | +20 / +20 | +20 / +20 | +20 / +20 | +20 / +20 | +1 / +1 | +5 / +1 | +27 / +28 |

| pool config | scenarios where marginal ≈ 0 (<$5) but naive ≥ $50 | median naive/marginal (both ≥ $5) | sign disagreements |
|---|---|---|---|
| own_context | 0 | 1.00 | 1 |
| snowflake_dedicated | 0 | 1.00 | 1 |
| snowflake_always_on_bi | 0 | 1.00 | 1 |
| attributed_per_second | 0 | 1.00 | 0 |
| bigquery_on_demand | 0 | 1.00 | 0 |
| bigquery_editions | 0 | 0.60 | 1 |
| databricks_sql_serverless | 0 | 1.00 | 1 |

Sensitivity to κ (snowflake_dedicated): truth marginal / naive attributed per scenario

| scenario | κ=10 | κ=100 | κ=1000 |
|---|---|---|---|
| s01_widen_date_filter | +9 / +9 | +90 / +90 | +885 / +897 |
| s02_remove_partition_pruning | +0 / +0 | +2 / +3 | +23 / +26 |
| s03_expand_incremental_window | +0 / +0 | +1 / +4 | +8 / +45 |
| s04_incremental_to_table | +5 / +5 | +47 / +49 | +450 / +493 |
| s05_many_to_many_join | +1 / +1 | +7 / +7 | +68 / +70 |
| s06_superlinear_self_join | +19 / +21 | +208 / +208 | +2036 / +2083 |
| s07_unnecessary_distinct | +0 / +0 | +3 / +2 | +26 / +23 |
| s08_expensive_window | +2 / +2 | +24 / +15 | +225 / +155 |
| s09_repeated_scans | +0 / +0 | +3 / +0 | +33 / +4 |
| s10_table_to_view | -1 / +6 | -11 / +57 | -107 / +568 |
| s11_view_to_table | +0 / -3 | +0 / -25 | +3 / -252 |
| s12_manual_predicate_pushdown | +0 / +0 | +0 / +0 | +1 / +0 |
| s13_select_fewer_columns | -3 / -3 | -30 / -30 | -285 / -297 |
| s14_join_preaggregation | -0 / -0 | -1 / -1 | -7 / -7 |
| s15_include_returns | -0 / -0 | -1 / -1 | -7 / -5 |
| s16_new_model | +1 / +1 | +7 / +7 | +69 / +71 |
| s17_monthly_job_regression | +0 / +0 | +1 / +1 | +14 / +15 |
| s18_frequent_cheap_view | -0 / +1 | -0 / +12 | -1 / +122 |
| s19_idle_capacity_absorbs | +0 / +2 | +0 / +17 | +0 / +167 |
| s20_bytes_up_capacity_pricing | +2 / +2 | +20 / +20 | +195 / +203 |
| s21_cosmetic_refactor | +0 / -0 | +0 / -0 | +1 / -4 |
| s22_sort_for_determinism | -2 / -2 | -24 / -24 | -229 / -235 |
| s23_macro_change | +0 / +0 | +0 / +1 | +4 / +11 |
| s24_var_default_change | +0 / +0 | +0 / +0 | +0 / +0 |
| s25_config_inheritance | +27 / +33 | +317 / +328 | +3182 / +3277 |
| s26_include_future_shipments | +2 / +2 | +20 / +20 | +189 / +202 |
