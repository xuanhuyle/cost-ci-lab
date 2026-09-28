| estimator | coverage | direction_acc_material | large_regression_recall | large_regression_recall_strict | false_warning_rate | bucket_exact | bucket_within_one | median_abs_log_error_material | within_2x_material | spearman_monthly_delta | ci_cost_x_prod_run_median | ci_cost_pct_of_monthly_median |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| static_cout | 1.00 | 0.62 | 0.78 | 0.67 | 0.10 | 0.50 | 0.69 | 1.81 | 0.20 | 0.64 | 0.00 | 0.00 |
| bytes_proxy | 1.00 | 0.75 | 0.78 | 0.67 | 0.30 | 0.42 | 0.77 | 0.24 | 0.69 | 0.79 | 0.00 | 0.00 |
| ab_bern01 | 1.00 | 0.69 | 0.78 | 0.67 | 0.00 | 0.65 | 0.77 | 0.73 | 0.46 | 0.63 | 0.14 | 0.27 |
| ab_recent90 | 1.00 | 0.75 | 0.78 | 0.44 | 0.10 | 0.58 | 0.77 | 0.54 | 0.67 | 0.58 | 3.37 | 5.66 |
| ab_key01 | 1.00 | 0.75 | 0.78 | 0.56 | 0.50 | 0.46 | 0.85 | 0.60 | 0.73 | 0.53 | 0.46 | 0.70 |
| ab_key10 | 1.00 | 0.88 | 1.00 | 0.78 | 0.20 | 0.65 | 0.85 | 0.35 | 0.60 | 0.81 | 1.63 | 4.11 |
| ab_two_point | 1.00 | 0.81 | 0.89 | 0.89 | 0.60 | 0.38 | 0.81 | 0.71 | 0.50 | 0.76 | 2.05 | 5.00 |
| hybrid | 1.00 | 0.88 | 1.00 | 0.89 | 0.10 | 0.69 | 0.88 | 0.13 | 0.93 | 0.84 | 4.00 | 1.62 |
| pr_vs_history | 1.00 | 0.94 | 0.89 | 0.78 | 0.20 | 0.65 | 0.96 | 0.14 | 0.88 | 0.87 | 2.49 | 5.02 |
| ab_full_anchored | 1.00 | 1.00 | 1.00 | 0.89 | 0.20 | 0.69 | 0.96 | 0.10 | 0.94 | 0.90 | 4.60 | 11.29 |
| ab_full_abs | 1.00 | 1.00 | 1.00 | 0.89 | 0.20 | 0.62 | 0.96 | 0.12 | 0.94 | 0.90 | 4.60 | 11.29 |
| lvl_direct | 1.00 | 0.75 | 0.67 | 0.67 | 0.20 | 0.54 | 0.85 | 0.17 | 0.92 | 0.58 | n/a | n/a |
| lvl_plus_1hop | 1.00 | 0.75 | 0.67 | 0.67 | 0.20 | 0.54 | 0.85 | 0.13 | 0.92 | 0.60 | n/a | n/a |
| lvl_all_models | 1.00 | 0.75 | 0.67 | 0.67 | 0.20 | 0.54 | 0.85 | 0.13 | 0.92 | 0.62 | n/a | n/a |
| lvl_all_with_consumers | 1.00 | 1.00 | 1.00 | 0.89 | 0.20 | 0.69 | 0.96 | 0.10 | 0.94 | 0.90 | n/a | n/a |

n=26 scenarios; material=16, immaterial=10, large regressions=9

Robustness: the same estimators scored against CPU-time (work) truth instead of latency:

| estimator | coverage | direction_acc_material | large_regression_recall | large_regression_recall_strict | false_warning_rate | bucket_exact | bucket_within_one | median_abs_log_error_material | within_2x_material | spearman_monthly_delta | ci_cost_x_prod_run_median | ci_cost_pct_of_monthly_median |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| static_cout | 1.00 | 0.55 | 0.73 | 0.64 | 0.17 | 0.38 | 0.69 | 1.66 | 0.27 | 0.64 | 0.00 | 0.00 |
| bytes_proxy | 1.00 | 0.65 | 0.82 | 0.55 | 0.17 | 0.42 | 0.65 | 0.83 | 0.38 | 0.66 | 0.00 | 0.00 |
| ab_bern01 | 1.00 | 0.75 | 0.91 | 0.55 | 0.33 | 0.42 | 0.73 | 0.96 | 0.47 | 0.68 | 0.05 | 0.13 |
| ab_recent90 | 1.00 | 0.85 | 0.82 | 0.82 | 0.17 | 0.62 | 0.85 | 0.38 | 0.68 | 0.72 | 2.19 | 3.84 |
| ab_key01 | 1.00 | 0.90 | 1.00 | 0.73 | 0.50 | 0.42 | 0.85 | 0.89 | 0.42 | 0.66 | 0.22 | 0.59 |
| ab_key10 | 1.00 | 0.95 | 1.00 | 0.91 | 0.17 | 0.73 | 0.92 | 0.36 | 0.70 | 0.89 | 0.84 | 2.26 |
| ab_two_point | 0.96 | 0.80 | 0.82 | 0.73 | 0.67 | 0.38 | 0.81 | 0.95 | 0.33 | 0.77 | 1.06 | 2.86 |
| hybrid | 1.00 | 0.95 | 1.00 | 0.91 | 0.00 | 0.77 | 0.96 | 0.07 | 0.89 | 0.91 | 3.03 | 3.30 |
| pr_vs_history | 1.00 | 1.00 | 1.00 | 0.91 | 0.17 | 0.65 | 0.92 | 0.12 | 0.90 | 0.97 | 2.40 | 6.19 |
| ab_full_anchored | 1.00 | 1.00 | 1.00 | 1.00 | 0.33 | 0.65 | 0.96 | 0.12 | 0.85 | 0.94 | 4.55 | 12.50 |
| ab_full_abs | 1.00 | 1.00 | 1.00 | 1.00 | 0.33 | 0.65 | 0.96 | 0.12 | 0.95 | 0.95 | 4.55 | 12.50 |

(CPU truth: material=20, immaterial=6, large=11)
