"""Experiment 10 (Phase 11): is the checker economical?

For a workload with production cost c per run and f runs/month, a pre-merge check that executes
k production-run-equivalents per CI analysis, triggered `pushes` times per PR, costs
    check = k * pushes * c.
The expected economic risk it removes, for a PR that touches the workload, is
    risk = P(material regression) * E[relative regression] * f * c * H
where H = months the regression would otherwise run before someone notices it.
Break-even frequency:  f* = k * pushes / (P * E[r] * H).
k is MEASURED in the lab per strategy (results/analysis.json, median CI lab-seconds / one production
run); P, E[r], H, pushes are ASSUMED and swept. Writes results/ci_economics.json.
"""
from __future__ import annotations

import json

from costci.paths import RESULTS

STRATEGIES = ["ab_full_abs", "pr_vs_history", "ab_key10", "hybrid", "static_cout"]


def main():
    a = json.loads((RESULTS / "analysis.json").read_text(encoding="utf-8"))
    k = {s: a["scores"][s]["ci_cost_x_prod_run_median"] for s in STRATEGIES}
    out = {"k_measured": k, "breakeven_runs_per_month": {}}
    grid = [(p, r, h, pushes) for p in (0.05, 0.2) for r in (0.5, 1.0) for h in (1, 3) for pushes in (1, 3)]
    for s, kv in k.items():
        rows = []
        for p, r, h, pushes in grid:
            f_star = (kv * pushes / (p * r * h)) if kv else 0.0
            rows.append({"p_regression": p, "mean_regression": r, "months_undetected": h,
                         "ci_runs_per_pr": pushes, "breakeven_runs_per_month": f_star})
        out["breakeven_runs_per_month"][s] = rows
    (RESULTS / "ci_economics.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("k (production-run equivalents per CI analysis):", {s: round(v or 0, 2) for s, v in k.items()})
    for s in STRATEGIES:
        fs = sorted(r["breakeven_runs_per_month"] for r in out["breakeven_runs_per_month"][s])
        print(f"{s:14s} break-even runs/month: min {fs[0]:8.1f}  median {fs[len(fs)//2]:8.1f}  max {fs[-1]:8.1f}")


if __name__ == "__main__":
    main()
