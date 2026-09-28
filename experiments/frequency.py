"""Experiment 6 (SIMULATED): how well can "runs per month" be extrapolated from run history?

Recurring cost = per-run delta x future frequency. Frequency must be inferred from telemetry
(query hashes, job runs). This experiment generates synthetic 180-day run histories for common
workload patterns, forecasts the next 30 days with simple deterministic estimators, and measures
error and interval coverage. It is a simulation: it shows *which patterns* are hard, not how often
they occur in real customers (UNVALIDATED).
Writes results/frequency.json.
"""
from __future__ import annotations

import json
import math
import random
import statistics as st

from costci.paths import RESULTS

DAYS_HIST, DAYS_FUT, TRIALS = 180, 30, 300


def poisson(rng, lam):
    # Knuth for small lambda, normal approximation for large
    if lam > 50:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    k, p, L = 0, 1.0, math.exp(-lam)
    while True:
        p *= rng.random()
        if p < L:
            return k
        k += 1


def daily_counts(pattern, rng):
    days = DAYS_HIST + DAYS_FUT
    out = []
    for d in range(days):
        dow = d % 7
        if pattern == "cron_daily":
            out.append(1)
        elif pattern == "cron_hourly_with_retries":
            out.append(24 + poisson(rng, 0.3))
        elif pattern == "monthly_job":
            out.append(1 if d % 30 == 0 else 0)
        elif pattern == "bi_weekday":
            lam = 2000 * (1.0 if dow < 5 else 0.2)
            out.append(poisson(rng, lam))
        elif pattern == "bi_growing_5pct_month":
            lam = 2000 * (1.0 if dow < 5 else 0.2) * (1.05 ** (d / 30))
            out.append(poisson(rng, lam))
        elif pattern == "seasonal_peak_in_forecast":
            lam = 500 * (3.0 if d >= DAYS_HIST else 1.0)          # e.g. November peak not in history
            out.append(poisson(rng, lam))
        elif pattern == "adhoc_sparse":
            out.append(poisson(rng, 4 / 90))                       # ~4 runs per quarter
        elif pattern == "data_arrival_driven":
            # rebuild only when upstream data arrives (dbt State / freshness-based orchestration)
            out.append(1 if rng.random() < (0.9 if dow < 5 else 0.1) else 0)
    return out


def forecasts(hist):
    last30, last90 = sum(hist[-30:]), sum(hist[-90:]) / 3
    n = len(hist)
    # Poisson-style 80% interval on the 90-day rate (normal approx on counts, floor at 0)
    lam = last90
    lo, hi = max(0.0, lam - 1.2816 * math.sqrt(max(lam, 1))), lam + 1.2816 * math.sqrt(max(lam, 1))
    # empirical interval from the spread of the six historical 30-day windows
    months = [sum(hist[i:i + 30]) for i in range(0, n - 29, 30)]
    elo, ehi = min(months), max(months)
    return {"trailing30": last30, "trailing90": last90, "poisson80": (lo, hi), "empirical_range": (elo, ehi)}


def main():
    patterns = ["cron_daily", "cron_hourly_with_retries", "monthly_job", "bi_weekday",
                "bi_growing_5pct_month", "seasonal_peak_in_forecast", "adhoc_sparse", "data_arrival_driven"]
    res = {}
    for pat in patterns:
        rng = random.Random(pat)
        errs30, errs90, cov_p, cov_e = [], [], [], []
        for _ in range(TRIALS):
            counts = daily_counts(pat, rng)
            hist, fut = counts[:DAYS_HIST], sum(counts[DAYS_HIST:])
            f = forecasts(hist)
            den = max(fut, 1)
            errs30.append(abs(f["trailing30"] - fut) / den)
            errs90.append(abs(f["trailing90"] - fut) / den)
            cov_p.append(f["poisson80"][0] <= fut <= f["poisson80"][1])
            cov_e.append(f["empirical_range"][0] <= fut <= f["empirical_range"][1])
        res[pat] = {"median_rel_err_trailing30": st.median(errs30),
                    "p90_rel_err_trailing30": sorted(errs30)[int(0.9 * TRIALS)],
                    "median_rel_err_trailing90": st.median(errs90),
                    "coverage_poisson80": sum(cov_p) / TRIALS,
                    "coverage_empirical_range": sum(cov_e) / TRIALS}
        print(f"{pat:28s}", {k: round(v, 3) for k, v in res[pat].items()})
    (RESULTS / "frequency.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
