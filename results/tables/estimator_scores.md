| estimator | coverage | direction_acc_material | large_regression_recall | large_regression_recall_strict | false_warning_rate | bucket_exact | bucket_within_one | median_abs_log_error_material | within_2x_material | spearman_monthly_delta | ci_cost_x_prod_run_median | ci_cost_pct_of_monthly_median |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| static_cout | 1.00 | 0.60 | 0.80 | 0.80 | 0.17 | 0.50 | 0.75 | 1.29 | 0.29 | 0.74 | 0.00 | 0.00 |
| bytes_proxy | 1.00 | 0.80 | 1.00 | 0.80 | 0.33 | 0.38 | 0.81 | 0.31 | 0.56 | 0.68 | 0.00 | 0.00 |
| ab_bern01 | 1.00 | 0.80 | 0.80 | 0.60 | 0.00 | 0.69 | 0.81 | 0.70 | 0.44 | 0.80 | 0.13 | 0.22 |
| ab_recent90 | 1.00 | 0.60 | 0.60 | 0.60 | 0.00 | 0.69 | 0.81 | 0.59 | 0.62 | 0.59 | 3.73 | 4.83 |
| ab_key01 | 1.00 | 0.80 | 0.60 | 0.60 | 0.33 | 0.69 | 0.88 | 0.27 | 0.78 | 0.67 | 0.44 | 0.60 |
| ab_key10 | 1.00 | 0.70 | 0.80 | 0.80 | 0.17 | 0.69 | 0.81 | 0.91 | 0.44 | 0.83 | 1.50 | 3.35 |
| ab_two_point | 1.00 | 0.80 | 1.00 | 0.80 | 0.33 | 0.56 | 0.62 | 1.10 | 0.38 | 0.76 | 2.02 | 3.83 |
| hybrid | 1.00 | 0.80 | 1.00 | 1.00 | 0.00 | 0.81 | 0.94 | 0.07 | 0.89 | 0.92 | 3.48 | 0.98 |
| pr_vs_history | 1.00 | 1.00 | 1.00 | 1.00 | 0.17 | 0.88 | 1.00 | 0.09 | 1.00 | 0.97 | 2.08 | 3.31 |
| ab_full_anchored | 1.00 | 1.00 | 1.00 | 1.00 | 0.17 | 0.81 | 1.00 | 0.10 | 0.90 | 0.79 | 4.13 | 9.08 |
| ab_full_abs | 1.00 | 1.00 | 1.00 | 1.00 | 0.17 | 0.81 | 1.00 | 0.12 | 1.00 | 0.79 | 4.13 | 9.08 |
| lvl_direct | 1.00 | 0.70 | 0.80 | 0.80 | 0.00 | 0.62 | 0.88 | 0.12 | 0.88 | 0.51 | n/a | n/a |
| lvl_plus_1hop | 1.00 | 0.70 | 0.80 | 0.80 | 0.00 | 0.69 | 0.88 | 0.12 | 0.88 | 0.47 | n/a | n/a |
| lvl_all_models | 1.00 | 0.70 | 0.80 | 0.80 | 0.00 | 0.69 | 0.88 | 0.10 | 1.00 | 0.47 | n/a | n/a |
| lvl_all_with_consumers | 1.00 | 1.00 | 1.00 | 1.00 | 0.17 | 0.81 | 1.00 | 0.10 | 0.90 | 0.79 | n/a | n/a |

n=16 scenarios; material=10, immaterial=6, large regressions=5

Robustness: the same estimators scored against CPU-time (work) truth instead of latency:

| estimator | coverage | direction_acc_material | large_regression_recall | large_regression_recall_strict | false_warning_rate | bucket_exact | bucket_within_one | median_abs_log_error_material | within_2x_material | spearman_monthly_delta | ci_cost_x_prod_run_median | ci_cost_pct_of_monthly_median |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| static_cout | 1.00 | 0.58 | 0.83 | 0.83 | 0.00 | 0.50 | 0.69 | 1.33 | 0.33 | 0.73 | 0.00 | 0.00 |
| bytes_proxy | 1.00 | 0.67 | 1.00 | 0.83 | 0.25 | 0.44 | 0.62 | 1.35 | 0.20 | 0.71 | 0.00 | 0.00 |
| ab_bern01 | 1.00 | 0.75 | 1.00 | 0.50 | 0.25 | 0.50 | 0.62 | 1.10 | 0.18 | 0.82 | 0.06 | 0.08 |
| ab_recent90 | 1.00 | 0.75 | 0.67 | 0.50 | 0.25 | 0.62 | 0.75 | 0.41 | 0.60 | 0.48 | 2.66 | 3.45 |
| ab_key01 | 1.00 | 1.00 | 1.00 | 0.67 | 0.25 | 0.56 | 0.88 | 0.65 | 0.58 | 0.76 | 0.22 | 0.50 |
| ab_key10 | 1.00 | 0.92 | 1.00 | 1.00 | 0.00 | 0.69 | 0.94 | 0.54 | 0.73 | 0.83 | 0.83 | 2.00 |
| ab_two_point | 0.94 | 0.75 | 0.83 | 0.83 | 0.75 | 0.31 | 0.81 | 0.99 | 0.36 | 0.73 | 1.02 | 2.50 |
| hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 0.75 | 1.00 | 0.06 | 0.92 | 0.96 | 3.12 | 3.06 |
| pr_vs_history | 1.00 | 1.00 | 1.00 | 1.00 | 0.50 | 0.62 | 1.00 | 0.12 | 0.92 | 0.99 | 2.18 | 4.21 |
| ab_full_anchored | 1.00 | 0.92 | 1.00 | 1.00 | 0.75 | 0.50 | 0.88 | 0.07 | 0.83 | 0.96 | 4.16 | 9.69 |
| ab_full_abs | 1.00 | 0.92 | 1.00 | 1.00 | 0.75 | 0.56 | 0.94 | 0.05 | 0.83 | 0.96 | 4.16 | 9.69 |

(CPU truth: material=12, immaterial=4, large=6)
