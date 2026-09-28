| estimator | 80% interval coverage | n | direction accuracy by confidence label |
|---|---|---|---|
| ab_full_anchored | 0.84 | 25 | HIGH: 1.00 (n=19), MEDIUM: 0.67 (n=6), LOW: n/a (n=0) |
| hybrid | 0.80 | 25 | HIGH: 0.94 (n=16), MEDIUM: 0.71 (n=7), LOW: 1.00 (n=2) |

| scenario | estimator | point | 80% interval | truth | inside | label |
|---|---|---|---|---|---|---|
| s01_widen_date_filter | ab_full_anchored | +99% | [+87%, +114%] | +111% | True | HIGH |
| s02_remove_partition_pruning | ab_full_anchored | -1% | [-7%, +5%] | +4% | True | HIGH |
| s03_expand_incremental_window | ab_full_anchored | -0% | [-8%, +10%] | +7% | True | HIGH |
| s04_incremental_to_table | ab_full_anchored | +57% | [+25%, +102%] | +62% | True | HIGH |
| s05_many_to_many_join | ab_full_anchored | +53% | [+41%, +65%] | +47% | True | HIGH |
| s06_superlinear_self_join | ab_full_anchored | +1419% | [+1295%, +1567%] | +1413% | True | HIGH |
| s07_unnecessary_distinct | ab_full_anchored | -2% | [-8%, +4%] | +3% | True | HIGH |
| s08_expensive_window | ab_full_anchored | +16% | [+4%, +30%] | +5% | True | MEDIUM |
| s09_repeated_scans | ab_full_anchored | -6% | [-15%, +7%] | -2% | True | MEDIUM |
| s10_table_to_view | ab_full_anchored | +118% | [+89%, +156%] | +118% | True | HIGH |
| s11_view_to_table | ab_full_anchored | -92% | [-102%, -83%] | -89% | True | HIGH |
| s12_manual_predicate_pushdown | ab_full_anchored | -12% | [-20%, -1%] | +0% | False | MEDIUM |
| s13_select_fewer_columns | ab_full_anchored | -42% | [-45%, -38%] | -40% | True | HIGH |
| s14_join_preaggregation | ab_full_anchored | -20% | [-26%, -14%] | -29% | False | HIGH |
| s15_include_returns | ab_full_anchored | -1% | [-7%, +5%] | -1% | True | HIGH |
| s17_monthly_job_regression | ab_full_anchored | +54% | [+43%, +67%] | +56% | True | HIGH |
| s18_frequent_cheap_view | ab_full_anchored | +64% | [+36%, +98%] | +77% | True | HIGH |
| s19_idle_capacity_absorbs | ab_full_anchored | +23% | [+6%, +43%] | +63% | False | MEDIUM |
| s20_bytes_up_capacity_pricing | ab_full_anchored | +18% | [+10%, +25%] | +25% | True | HIGH |
| s21_cosmetic_refactor | ab_full_anchored | +2% | [-9%, +17%] | -1% | True | MEDIUM |
| s22_sort_for_determinism | ab_full_anchored | -19% | [-23%, -14%] | -27% | False | HIGH |
| s23_macro_change | ab_full_anchored | +2% | [-5%, +10%] | +1% | True | HIGH |
| s24_var_default_change | ab_full_anchored | +6% | [-9%, +25%] | +0% | True | MEDIUM |
| s25_config_inheritance | ab_full_anchored | +83% | [+72%, +99%] | +94% | True | HIGH |
| s26_include_future_shipments | ab_full_anchored | +30% | [+23%, +39%] | +33% | True | HIGH |
| s01_widen_date_filter | hybrid | +98% | [+85%, +112%] | +111% | True | HIGH |
| s02_remove_partition_pruning | hybrid | -5% | [-10%, +1%] | +4% | False | MEDIUM |
| s03_expand_incremental_window | hybrid | +1% | [-7%, +11%] | +7% | True | MEDIUM |
| s04_incremental_to_table | hybrid | +52% | [+19%, +95%] | +62% | True | HIGH |
| s05_many_to_many_join | hybrid | +53% | [+40%, +65%] | +47% | True | HIGH |
| s06_superlinear_self_join | hybrid | +1419% | [+1297%, +1557%] | +1413% | True | HIGH |
| s07_unnecessary_distinct | hybrid | +1% | [-4%, +8%] | +3% | True | HIGH |
| s08_expensive_window | hybrid | +16% | [+5%, +30%] | +5% | True | MEDIUM |
| s09_repeated_scans | hybrid | +2% | [-9%, +15%] | -2% | True | MEDIUM |
| s10_table_to_view | hybrid | +63% | [+44%, +89%] | +118% | False | HIGH |
| s11_view_to_table | hybrid | -92% | [-102%, -83%] | -89% | True | HIGH |
| s12_manual_predicate_pushdown | hybrid | +0% | [-9%, +12%] | +0% | True | MEDIUM |
| s13_select_fewer_columns | hybrid | -42% | [-46%, -39%] | -40% | True | HIGH |
| s14_join_preaggregation | hybrid | +21% | [+12%, +31%] | -29% | False | HIGH |
| s15_include_returns | hybrid | +0% | [-6%, +6%] | -1% | True | HIGH |
| s17_monthly_job_regression | hybrid | +54% | [+42%, +67%] | +56% | True | HIGH |
| s18_frequent_cheap_view | hybrid | +64% | [+37%, +98%] | +77% | True | HIGH |
| s19_idle_capacity_absorbs | hybrid | +23% | [+6%, +42%] | +63% | False | MEDIUM |
| s20_bytes_up_capacity_pricing | hybrid | +20% | [+12%, +28%] | +25% | True | HIGH |
| s21_cosmetic_refactor | hybrid | -0% | [-11%, +15%] | -1% | True | LOW |
| s22_sort_for_determinism | hybrid | +6% | [-1%, +13%] | -27% | False | MEDIUM |
| s23_macro_change | hybrid | -0% | [-6%, +7%] | +1% | True | HIGH |
| s24_var_default_change | hybrid | +3% | [-12%, +20%] | +0% | True | LOW |
| s25_config_inheritance | hybrid | +82% | [+71%, +98%] | +94% | True | HIGH |
| s26_include_future_shipments | hybrid | +26% | [+19%, +34%] | +33% | True | HIGH |
