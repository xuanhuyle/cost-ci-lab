"""Score the public-PR experiment against the pre-registered metrics.

Reads results/public_pr/measurements.json and writes results/public_pr/scores.json plus a
markdown table. Development and holdout are scored separately and never pooled.

Thresholds are imported from costci.metrics, unchanged from baseline 0ea6284.
"""
from __future__ import annotations

import json
import math
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from costci.metrics import LARGE, MATERIAL, bucket, direction, spearman  # noqa: E402
from costci.pools import Execution, bill  # noqa: E402

RES = ROOT / "results" / "public_pr"
RUNS_PER_MONTH = 30                      # SHADOW_ASSUMPTION: the job runs daily
DAY_S = 24 * 3600
JOB_START_S = 2 * 3600                   # SHADOW_ASSUMPTION: the job starts at 02:00 each day
# SHADOW_ASSUMPTION: one dedicated, time-metered warehouse. Rates are the documented
# Snowflake dedicated-warehouse rules (E-011) at an X-Small rate and a list credit price.
SHADOW_POOL = {"kind": "snowflake_warehouse", "credits_per_hour": 1.0,
               "price_per_credit": 3.0, "auto_suspend_s": 600, "min_billing_s": 60,
               "max_clusters": 1}


DOLLARS_PER_SECOND = SHADOW_POOL["credits_per_hour"] * SHADOW_POOL["price_per_credit"] / 3600


def shadow_month_dollars_standalone(per_run_seconds: float) -> float:
    """Replay a month of the affected workload as if it were its own scheduled job.

    This is the *attributed* view: it carries the warehouse's 60-second minimum and its
    AUTO_SUSPEND idle tail, so for a short workload the bill is dominated by idle rather than by
    the change. Reported for contrast, not used for materiality.
    """
    if per_run_seconds is None:
        return None
    execs = [Execution(workload="job", start_s=d * DAY_S + JOB_START_S,
                       duration_s=per_run_seconds) for d in range(RUNS_PER_MONTH)]
    return bill(SHADOW_POOL, execs)["dollars"]


def shadow_month_dollars_marginal(delta_seconds: float) -> float:
    """The *marginal* view: the affected nodes run inside the project's daily job, so the
    warehouse is already running. The marginal bill of the change is its extra engine seconds.

    E-038 showed these two views can differ by orders of magnitude and even in sign; both are
    reported here for the same reason.
    """
    if delta_seconds is None:
        return None
    return delta_seconds * RUNS_PER_MONTH * DOLLARS_PER_SECOND


def frac(bools: list[bool]) -> float | None:
    return sum(bools) / len(bools) if bools else None


def rows_for(ms: list[dict], split: str) -> list[dict]:
    out = []
    for m in ms:
        if m.get("split") != split or m.get("outcome") != "OK":
            continue
        pred, truth = m.get("prediction"), m.get("truth")
        if not pred or not truth or pred.get("rel") is None or truth.get("rel") is None:
            continue
        out.append({
            "pr": m["pr"], "merged_at": m["merged_at"], "n_affected": m["n_affected"],
            "pred_rel": pred["rel"], "truth_rel": truth["rel"],
            "pred_delta": pred["delta_s"] * RUNS_PER_MONTH,
            "truth_delta": truth["delta_s"] * RUNS_PER_MONTH,
            "pred_month_dollars_marginal": shadow_month_dollars_marginal(pred["delta_s"]),
            "truth_month_dollars_marginal": shadow_month_dollars_marginal(truth["delta_s"]),
            "pred_month_dollars_attributed": (
                shadow_month_dollars_standalone(pred["pr"]["median_s"])
                - shadow_month_dollars_standalone(pred["main"]["median_s"])),
            "truth_month_dollars_attributed": (
                shadow_month_dollars_standalone(truth["pr"]["median_s"])
                - shadow_month_dollars_standalone(truth["main"]["median_s"])),
            "pred_base": pred["main"]["median_s"], "truth_base": truth["main"]["median_s"],
            "grade": pred.get("grade"), "k": pred.get("k_production_runs"),
            "k_job": pred.get("k_full_job_runs"),
            "analysis_wall_s": pred.get("analysis_wall_s"),
            "analysis_engine_s": pred.get("analysis_engine_s"),
            "touched": m.get("touched", {}),
        })
    return out


def score(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    td = [direction(r["truth_rel"]) for r in rows]
    pd_ = [direction(r["pred_rel"]) for r in rows]
    material = [i for i in range(n) if td[i] != "immaterial"]
    immaterial = [i for i in range(n) if td[i] == "immaterial"]
    mat_up = [i for i in range(n) if td[i] == "increase"]
    large = [i for i in range(n) if rows[i]["truth_rel"] >= LARGE]
    errs, flips = [], 0
    for i in material:
        p, t = rows[i]["pred_delta"], rows[i]["truth_delta"]
        if p is None or t in (None, 0):
            continue
        if p * t <= 0:
            flips += 1
        else:
            errs.append(abs(math.log(p / t)))
    hi = [i for i in range(n) if rows[i]["grade"] == "HIGH"]
    lo = [i for i in range(n) if rows[i]["grade"] != "HIGH"]
    out = {
        "n": n, "n_material": len(material), "n_immaterial": len(immaterial),
        "n_material_increase": len(mat_up), "n_large": len(large),
        "direction_acc_material": frac([pd_[i] == td[i] for i in material]),
        "direction_acc_all": frac([pd_[i] == td[i] for i in range(n)]),
        "material_regression_recall": frac([pd_[i] == "increase" for i in mat_up]),
        "large_regression_recall": frac([pd_[i] == "increase" for i in large]),
        "false_warning_rate": frac([pd_[i] != "immaterial" for i in immaterial]),
        "bucket_exact": frac([bucket(rows[i]["pred_rel"]) == bucket(rows[i]["truth_rel"])
                              for i in range(n)]),
        "bucket_within_one": frac([abs(bucket(rows[i]["pred_rel"]) - bucket(rows[i]["truth_rel"])) <= 1
                                   for i in range(n)]),
        "transfer_median_abs_log_error": st.median(errs) if errs else None,
        "transfer_sign_flips": flips,
        "spearman_delta": spearman([r["pred_delta"] for r in rows], [r["truth_delta"] for r in rows]),
        "direction_acc_HIGH": frac([pd_[i] == td[i] for i in hi]),
        "direction_acc_not_HIGH": frac([pd_[i] == td[i] for i in lo]),
        "n_HIGH": len(hi), "n_not_HIGH": len(lo),
        "k_affected_median": st.median([r["k"] for r in rows if r["k"]]) if any(r["k"] for r in rows) else None,
        "k_job_median": (st.median([r["k_job"] for r in rows if r["k_job"]])
                         if any(r["k_job"] for r in rows) else None),
        "k_job_max": max([r["k_job"] for r in rows if r["k_job"]], default=None),
        "analysis_wall_s_median": st.median([r["analysis_wall_s"] for r in rows]),
    }
    out.update(economics(rows))
    return out


def economics(rows: list[dict]) -> dict:
    """Shadow-environment economics. SHADOW_ASSUMPTION throughout; not customer ROI.

    avoidable cost = the realised monthly shadow dollars of the material regressions that the
    method correctly flagged, i.e. what a gate that blocked them would have prevented in the
    first month. analysis cost = the engine seconds spent analysing every PR in the set, priced
    on the same pool.
    """
    analysis_s = sum(r["analysis_engine_s"] or 0.0 for r in rows)
    analysis_dollars = analysis_s * DOLLARS_PER_SECOND
    caught, missed = 0.0, 0.0
    for r in rows:
        if direction(r["truth_rel"]) != "increase":
            continue
        d = r["truth_month_dollars_marginal"] or 0.0
        if direction(r["pred_rel"]) == "increase":
            caught += d
        else:
            missed += d
    return {"analysis_engine_seconds_total": round(analysis_s, 1),
            "analysis_dollars_shadow": round(analysis_dollars, 4),
            "avoided_shadow_dollars_month": round(caught, 4),
            "missed_shadow_dollars_month": round(missed, 4),
            "avoided_over_analysis": (caught / analysis_dollars) if analysis_dollars else None}


def comparator_highcost(rows: list[dict], T: float) -> dict:
    """C1: flag a PR if any affected workload's production baseline cost exceeds T seconds."""
    n = len(rows)
    td = [direction(r["truth_rel"]) for r in rows]
    flagged = [r["truth_base"] is not None and r["truth_base"] >= T for r in rows]
    mat_up = [i for i in range(n) if td[i] == "increase"]
    immaterial = [i for i in range(n) if td[i] == "immaterial"]
    return {"T_seconds": T, "n_flagged": sum(flagged),
            "material_regression_recall": frac([flagged[i] for i in mat_up]),
            "false_warning_rate": frac([flagged[i] for i in immaterial])}


def comparator_blastsize(rows: list[dict], N: int) -> dict:
    """C2': a no-execution rule. Flag a PR if its affected node set is at least N nodes.

    The brief asks for the cheapest estimator in the repo that needs no counterfactual
    execution. The static-plan and byte estimators of `costci/estimators.py` operate on
    per-statement DuckDB profiles, which this adapter does not produce (real dbt executes the
    models). The nearest computable no-execution predictor is blast-radius size, which is
    available from change detection alone.
    """
    n = len(rows)
    td = [direction(r["truth_rel"]) for r in rows]
    flagged = [r["n_affected"] >= N for r in rows]
    mat_up = [i for i in range(n) if td[i] == "increase"]
    immaterial = [i for i in range(n) if td[i] == "immaterial"]
    return {"N_nodes": N, "n_flagged": sum(flagged),
            "material_regression_recall": frac([flagged[i] for i in mat_up]),
            "false_warning_rate": frac([flagged[i] for i in immaterial])}


def choose_N(dev_rows: list[dict]) -> int:
    cands = sorted({r["n_affected"] for r in dev_rows})
    best, bestf1 = (cands[0] if cands else 1), -1.0
    for N in cands:
        c = comparator_blastsize(dev_rows, N)
        rec, fp = c["material_regression_recall"], c["false_warning_rate"]
        if rec is None:
            continue
        f1 = 0.0 if (rec + 1 - (fp or 0.0)) == 0 else             2 * rec * (1 - (fp or 0.0)) / (rec + 1 - (fp or 0.0))
        if f1 > bestf1:
            best, bestf1 = N, f1
    return best


def choose_T(dev_rows: list[dict]) -> float:
    """Pick T on the development set only, maximising F1 against material increases."""
    cands = sorted({round(r["truth_base"], 4) for r in dev_rows if r["truth_base"] is not None})
    best, bestf1 = (cands[0] if cands else 0.0), -1.0
    for T in cands:
        c = comparator_highcost(dev_rows, T)
        rec, fp = c["material_regression_recall"], c["false_warning_rate"]
        if rec is None:
            continue
        prec_proxy = 1.0 - (fp or 0.0)
        f1 = 0.0 if (rec + prec_proxy) == 0 else 2 * rec * prec_proxy / (rec + prec_proxy)
        if f1 > bestf1:
            best, bestf1 = T, f1
    return best


def md_table(d: dict, title: str) -> str:
    lines = [f"**{title}**", "", "| metric | value |", "|---|---|"]
    for k, v in d.items():
        lines.append(f"| {k} | {v if not isinstance(v, float) else round(v, 4)} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ms = json.loads((RES / "measurements.json").read_text(encoding="utf-8"))
    dev, hold = rows_for(ms, "development"), rows_for(ms, "holdout")
    out = {"runs_per_month_shadow_assumption": RUNS_PER_MONTH,
           "material_threshold": MATERIAL, "large_threshold": LARGE,
           "development": score(dev), "holdout": score(hold),
           "outcomes": {}}
    for m in ms:
        out["outcomes"][str(m["pr"])] = m.get("outcome", "?")
    if dev:
        T = choose_T(dev)
        out["comparator_C1"] = {"T_chosen_on_development": T,
                                "development": comparator_highcost(dev, T),
                                "holdout": comparator_highcost(hold, T) if hold else None}
        N = choose_N(dev)
        out["comparator_C2"] = {"N_chosen_on_development": N,
                                "development": comparator_blastsize(dev, N),
                                "holdout": comparator_blastsize(hold, N) if hold else None}
    out["rows"] = {"development": dev, "holdout": hold}
    (RES / "scores.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    md = md_table(out["development"], "Development set") + "\n" + \
        md_table(out["holdout"], "Locked holdout")
    if out.get("comparator_C1"):
        md += "\n" + md_table(out["comparator_C1"]["holdout"] or {},
                              f"Comparator C1 on holdout (T={out['comparator_C1']['T_chosen_on_development']}s)")
    (RES / "scores.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
