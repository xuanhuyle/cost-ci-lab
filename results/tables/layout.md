| scenario | ratio, default row groups (~26 days) | ratio, 8,192-row groups (~1.7 days) |
|---|---|---|
| s01_widen_date_filter | 2.502 | 2.386 |
| s02_remove_partition_pruning | 0.994 | 1.011 |
| s03_expand_incremental_window | 1.208 | 1.166 |
| s04_incremental_to_table | 5.878 | 5.775 |
| s13_select_fewer_columns | 0.581 | 0.596 |
| s24_var_default_change | n/a | n/a |
