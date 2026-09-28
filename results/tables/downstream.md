| scenario | truth | direct | plus_1hop | all_models | all_with_consumers | elasticity_prod | elasticity_key10 |
|---|---|---|---|---|---|---|---|
| s01_widen_date_filter | +111% | +87% | +98% | +98% | +99% | +193% | +193% |
| s02_remove_partition_pruning | +4% | -0% | -1% | -1% | -1% | -0% | -0% |
| s03_expand_incremental_window | +7% | +3% | +3% | +3% | -0% | +3% | +3% |
| s04_incremental_to_table | +62% | +52% | +52% | +52% | +57% | +52% | +52% |
| s07_unnecessary_distinct | +3% | +0% | -2% | -2% | -2% | +0% | +0% |
| s08_expensive_window | +5% | +16% | +16% | +16% | +16% | +16% | +16% |
| s09_repeated_scans | -2% | +2% | +0% | -0% | -6% | +2% | +2% |
| s10_table_to_view | +118% | -10% | -10% | -10% | +118% | -10% | -10% |
| s11_view_to_table | -89% | +1% | +1% | +1% | -92% | +1% | +1% |
| s12_manual_predicate_pushdown | +0% | -10% | -10% | -10% | -12% | -10% | -10% |
| s13_select_fewer_columns | -40% | -42% | -42% | -42% | -42% | -42% | -42% |
| s15_include_returns | -1% | +0% | -1% | -1% | -1% | +0% | +0% |
| s18_frequent_cheap_view | +77% | +0% | +0% | +0% | +64% | +0% | +0% |
| s19_idle_capacity_absorbs | +63% | -0% | -0% | -0% | +23% | -0% | -0% |
| s20_bytes_up_capacity_pricing | +25% | +20% | +18% | +18% | +18% | +20% | +20% |
| s21_cosmetic_refactor | -1% | -0% | -0% | -0% | +2% | -0% | -0% |
| s22_sort_for_determinism | -27% | -23% | -19% | -19% | -19% | -23% | -23% |
| s23_macro_change | +1% | -0% | -1% | -1% | +2% | -0% | -0% |
| s24_var_default_change | +0% | +1% | +1% | +1% | +6% | +1% | +1% |
| s25_config_inheritance | +94% | +82% | +83% | +83% | +83% | +82% | +82% |
| s26_include_future_shipments | +33% | +20% | +25% | +25% | +30% | +30% | +30% |

CI execution (lab-seconds, MAIN+PR once) by strategy:

| scenario | direct | plus_1hop | all_models | all_with_consumers | elasticity |
|---|---|---|---|---|---|
| s01_widen_date_filter | 18.2 | 22.9 | 22.9 | 22.9 | 18.2 |
| s02_remove_partition_pruning | 10.6 | 14.2 | 14.2 | 14.2 | 10.6 |
| s03_expand_incremental_window | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 |
| s04_incremental_to_table | 0.3 | 0.3 | 0.3 | 0.3 | 0.3 |
| s07_unnecessary_distinct | 10.9 | 14.6 | 14.6 | 14.6 | 10.9 |
| s08_expensive_window | 3.7 | 5.9 | 6.5 | 6.5 | 3.7 |
| s09_repeated_scans | 1.8 | 4.1 | 4.6 | 4.7 | 1.8 |
| s10_table_to_view | 1.2 | 1.7 | 1.7 | 1.8 | 1.2 |
| s11_view_to_table | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 |
| s12_manual_predicate_pushdown | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 |
| s13_select_fewer_columns | 7.7 | 11.3 | 11.3 | 11.3 | 7.7 |
| s15_include_returns | 11.4 | 15.1 | 15.1 | 15.1 | 11.4 |
| s18_frequent_cheap_view | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| s19_idle_capacity_absorbs | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| s20_bytes_up_capacity_pricing | 13.7 | 17.5 | 17.5 | 17.5 | 13.7 |
| s21_cosmetic_refactor | 1.6 | 4.1 | 4.7 | 4.7 | 1.6 |
| s22_sort_for_determinism | 10.2 | 14.1 | 14.1 | 14.1 | 10.2 |
| s23_macro_change | 30.3 | 34.1 | 34.1 | 34.1 | 30.3 |
| s24_var_default_change | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 |
| s25_config_inheritance | 32.2 | 78.2 | 83.1 | 83.2 | 32.2 |
| s26_include_future_shipments | 10.2 | 13.7 | 13.7 | 13.8 | 10.2 |
