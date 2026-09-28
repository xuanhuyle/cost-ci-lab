| scenario | prod 4 threads (ref) | CI 1 thread | prod under load | cold single run |
|---|---|---|---|---|
| s01_widen_date_filter | 2.361 | 2.995 (+27%) | 1.947 (-18%) | 2.135 (-10%) |
| s04_incremental_to_table | 6.783 | 15.979 (+136%) | 10.696 (+58%) | 4.787 (-29%) |
| s05_many_to_many_join | 1.674 | 1.936 (+16%) | 1.584 (-5%) | 1.628 (-3%) |
| s08_expensive_window | 2.257 | 3.441 (+52%) | 2.516 (+12%) | 1.998 (-11%) |
| s09_repeated_scans | 1.262 | 1.276 (+1%) | 1.276 (+1%) | 1.257 (-0%) |
| s22_sort_for_determinism | 0.812 | 1.095 (+35%) | 0.902 (+11%) | 0.777 (-4%) |

Cell = PR/MAIN total-latency ratio (difference vs the production reference).

| scenario | slowdown of MAIN under load | slowdown of PR under load |
|---|---|---|
| s01_widen_date_filter | 3.65x | 2.61x |
| s04_incremental_to_table | 2.88x | 4.53x |
| s05_many_to_many_join | 3.44x | 3.18x |
| s08_expensive_window | 3.41x | 4.24x |
| s09_repeated_scans | 3.11x | 3.37x |
| s22_sort_for_determinism | 3.26x | 3.44x |
