"""Experiment 5: can confidence be grounded quantitatively? (Phase 7)

For the history-anchored full-clone estimator (and the hybrid), build an 80% interval per scenario
from *measured* noise only:
  * single-CI-run noise: log-SD of repeated runs as a function of duration (noise model fitted
    on MAIN reps in results/analysis.json)
  * anchor noise: the same model, averaged over the 3 history reps
  * scale-transfer noise (sample paths of the hybrid): |log r_key10 - log r_key01|
Intervals come from Monte Carlo propagation. We then check (a) coverage of the measured truth and
(b) whether a confidence label derived from the interval predicts correctness.
Writes results/uncertainty.json.
"""
from __future__ import annotations

import json
import math
import random
import statistics as st

from costci import metrics
from costci.paths import RESULTS

N = 4000
Q = (0.10, 0.90)


def sigma(noise_model, d):
    for lo, hi, s, _ in noise_model:
        if lo <= (d or 0) < hi:
            return s
    return noise_model[-1][2]


def interval(rows, noise_model, est_key, rng):
    base = sum(w["runs_per_month"] * w["truth_main_s"] for w in rows)
    sims = []
    for _ in range(N):
        tot = 0.0
        for w in rows:
            e = w[f"est_{est_key}"]
            if e is None:
                continue
            h = w["anchor_s"]
            if not h:                     # new workload: absolute measurement noise only
                tot += w["runs_per_month"] * e * math.exp(rng.gauss(0, sigma(noise_model, e)))
                continue
            r = 1 + e / h
            s_ci = sigma(noise_model, h) * math.sqrt(2)
            s_h = sigma(noise_model, h) / math.sqrt(3)
            extra = w.get("transfer_sigma", 0.0) if est_key == "hybrid" and w.get("hybrid_path") == "sample" else 0.0
            r_s = r * math.exp(rng.gauss(0, math.hypot(s_ci, extra)))
            h_s = h * math.exp(rng.gauss(0, s_h))
            tot += w["runs_per_month"] * h_s * (r_s - 1)
        sims.append(tot / base if base else (math.inf if tot > 0 else 0.0))
    sims.sort()
    return sims[int(Q[0] * N)], sims[int(Q[1] * N)], st.median(sims)


def label(lo, hi):
    classes = {metrics.direction(lo), metrics.direction(hi)}
    if lo < -metrics.MATERIAL and hi > metrics.MATERIAL:
        return "LOW"
    return "HIGH" if len(classes) == 1 else "MEDIUM"


def main():
    a = json.loads((RESULTS / "analysis.json").read_text(encoding="utf-8"))
    nm = a["noise_model"]
    rng = random.Random(7)
    by = {}
    for w in a["workloads"]:
        by.setdefault(w["scenario"], []).append(w)
    out = {"rows": [], "summary": {}}
    for est in ("ab_full_anchored", "hybrid"):
        cover, lab = [], {"HIGH": [], "MEDIUM": [], "LOW": []}
        for r in a["rows"]:
            rows = by[r["id"]]
            truth = r["truth_rel"]
            if truth is None or math.isinf(truth):
                continue
            lo, hi, mid = interval(rows, nm, est, rng)
            inside = lo <= truth <= hi
            point = r.get(f"{est}_rel")
            correct = metrics.direction(point) == metrics.direction(truth)
            lbl = label(lo, hi)
            cover.append(inside)
            lab[lbl].append(correct)
            out["rows"].append({"scenario": r["id"], "estimator": est, "lo": lo, "hi": hi, "point": point,
                                "truth": truth, "inside": inside, "label": lbl, "direction_correct": correct})
        out["summary"][est] = {
            "coverage_80": sum(cover) / len(cover) if cover else None, "n": len(cover),
            "direction_acc_by_label": {k: (sum(v) / len(v) if v else None, len(v)) for k, v in lab.items()},
        }
        print(est, out["summary"][est])
    (RESULTS / "uncertainty.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
