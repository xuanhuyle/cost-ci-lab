"""Experiment 7: post-merge calibration loop (Phase 10), on the lab's predicted-vs-realised pairs.

Loop:  pre-merge prediction -> merge -> production runs -> realised usage -> error -> correction.
Here "realised" is the measured production truth for each scenario's workloads. We test whether a
simple, deterministic correction learned from *other* changes improves a new change's estimate:
  global     one multiplicative factor per estimator (median truth/estimate ratio)
  by_class   one factor per workload class (table / incremental / view-or-consumer)
evaluated leave-one-scenario-out. With 25 synthetic changes on one engine this can only show
whether systematic bias exists and is learnable locally; it says nothing about cross-customer
transfer (no such data exists here). Writes results/calibration.json.
"""
from __future__ import annotations

import json
import math
import statistics as st

from costci.paths import RESULTS

ESTIMATORS = ["ab_full_anchored", "hybrid", "ab_two_point", "ab_key10", "static_cout", "bytes_proxy"]


def wclass(w):
    if w["kind"] == "consumer":
        return "consumer"
    return w["materialized_pr"] or w["materialized_main"] or "table"


def pairs(workloads, est):
    out = []
    for w in workloads:
        e = w.get(f"est_{est}")
        t = w["truth_pr_s"] - w["truth_main_s"]
        base = w["truth_main_s"] or w["truth_pr_s"]
        # only material, same-sign pairs carry a usable multiplicative signal
        if e is None or not base or abs(t) < 0.1 * base or e * t <= 0:
            continue
        out.append({"scenario": w["scenario"], "class": wclass(w), "log_ratio": math.log(t / e),
                    "err_before": abs(math.log(t / e))})
    return out


def main():
    a = json.loads((RESULTS / "analysis.json").read_text(encoding="utf-8"))
    res = {}
    for est in ESTIMATORS:
        ps = pairs(a["workloads"], est)
        if len(ps) < 5:
            continue
        after_g, after_c, before = [], [], []
        for p in ps:
            train = [q for q in ps if q["scenario"] != p["scenario"]]
            g = st.median(q["log_ratio"] for q in train)
            same = [q["log_ratio"] for q in train if q["class"] == p["class"]]
            c = st.median(same) if len(same) >= 3 else g
            before.append(p["err_before"])
            after_g.append(abs(p["log_ratio"] - g))
            after_c.append(abs(p["log_ratio"] - c))
        res[est] = {"n_pairs": len(ps),
                    "median_abs_log_err_before": st.median(before),
                    "median_abs_log_err_global": st.median(after_g),
                    "median_abs_log_err_by_class": st.median(after_c),
                    "learned_global_factor": math.exp(st.median(q["log_ratio"] for q in ps))}
        print(est, {k: round(v, 3) if isinstance(v, float) else v for k, v in res[est].items()})
    (RESULTS / "calibration.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
