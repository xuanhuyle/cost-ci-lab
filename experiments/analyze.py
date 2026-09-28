"""Experiment 1 analysis: score every estimator against measured ground truth.

Reads results/bench/*.json (+ results/baseline.json for the economics layer) and writes
results/analysis.json plus markdown tables in results/tables/.

Unit of the resource layer: workload-seconds per month = sum over affected workloads of
(runs per month x per-run engine latency). This equals cost under pure per-second pricing
(Snowflake attribution view, serverless per-query billing); pool effects are analysed separately.
"""
from __future__ import annotations

import json
import math
import random
import re
import statistics as st
from pathlib import Path

from costci import economics, metrics
from costci.estimators import (CI_REP, ESTIMATORS, HIST_REPS, TRUTH_REPS, ScenarioData,
                               est_ab_full_anchored, est_ab_two_point, _vals, med, set_metric)
from costci.paths import DATA, RESULTS

TABLES = RESULTS / "tables"
REL_RE = re.compile(r'"lab"\."ci_pr"\."([a-z0-9_]+)"')


def load() -> tuple[list[ScenarioData], dict]:
    envs = json.loads((DATA / "environments.json").read_text())
    prod_li = envs["prod"]["rows"]["lineitem"]
    env_rows = {e: envs[e]["rows"]["lineitem"] / prod_li for e in envs if not e.startswith("_")}
    # A scenario re-measured with union change detection (dbt state missed its change) replaces
    # the dbt-state record: estimators need the truly affected workloads to be measured.
    paths = {p.name: p for p in sorted((RESULTS / "bench").glob("s*.json"))}
    paths.update({p.name: p for p in sorted((RESULTS / "bench_union").glob("s*.json"))})
    sds = [ScenarioData(json.loads(paths[k].read_text(encoding="utf-8")), env_rows) for k in sorted(paths)]
    return sds, env_rows


# --------------------------------------------------------------------------- calibrations
def global_calibration(sds):
    """Seconds per unit of static signal, fitted on production *history* of MAIN only."""
    per_cout, per_byte = [], []
    for sd in sds:
        for wid in sd.workloads:
            if not sd.in_variant(wid, "main"):
                continue
            h = sd.anchor(wid)
            cm, _ = sd.explain_cout(wid)
            b = med(_vals(sd.runs("prod"), "main", wid, HIST_REPS, "logical_bytes"))
            if h and cm:
                per_cout.append(h / cm)
            if h and b:
                per_byte.append(h / b)
    return (st.median(per_cout) if per_cout else None, st.median(per_byte) if per_byte else None)


def noise_model(sds):
    """Pooled log-SD of repeated MAIN runs (hist+truth reps) by duration band -> sigma(duration)."""
    pts = []
    for sd in sds:
        for wid in sd.workloads:
            xs = _vals(sd.runs("prod"), "main", wid, HIST_REPS + TRUTH_REPS)
            if xs and len(xs) >= 4 and min(xs) > 0:
                logs = [math.log(x) for x in xs]
                pts.append((st.median(xs), st.pstdev(logs)))
    bands = [(0, 0.01), (0.01, 0.1), (0.1, 1), (1, 100)]
    model = []
    for lo, hi in bands:
        s = [sig for d, sig in pts if lo <= d < hi]
        model.append((lo, hi, st.median(s) if s else 0.3, len(s)))
    return model


def sigma_for(model, d):
    for lo, hi, s, _ in model:
        if lo <= (d or 0) < hi:
            return s
    return model[-1][2]


# --------------------------------------------------------------------------- per-workload tables
def distances(sd: ScenarioData) -> dict[str, int]:
    """Hop distance of each PR workload from the modified models (consumers get their own tier)."""
    modified = set(sd.rec["changes"]["modified"])
    parents = {}
    for wid, w in sd.workloads.items():
        meta = w.get("pr") or w.get("main")
        refs = set(REL_RE.findall(meta["sql"])) if "pr" in w else set()
        parents[wid] = {f"model:{r}" for r in refs}
    dist = {}

    def d(wid, seen=()):
        if wid in dist:
            return dist[wid]
        meta = sd.meta(wid)
        if meta["kind"] == "model" and meta["name"] in modified:
            dist[wid] = 0
            return 0
        ps = [p for p in parents.get(wid, ()) if p in sd.workloads and p not in seen]
        val = 1 + min((d(p, seen + (wid,)) for p in ps), default=98)
        dist[wid] = val
        return val
    for wid in sd.workloads:
        d(wid)
    return dist


def hybrid(sd, wid, cal, ci_cost):
    """Static screen -> key-consistent samples (two-point) -> escalate to full clone if risky."""
    meta = sd.meta(wid)
    cm, cp = sd.explain_cout(wid)
    shp = sd.explain_shape(wid)
    bm, bp = (med(_vals(sd.runs("prod"), v, wid, CI_REP, "logical_bytes")) for v in ("main", "pr"))
    new = not sd.in_variant(wid, "main")
    static_same = (not new and cm and cp and abs(cp / cm - 1) < 0.05 and shp[0] == shp[1]
                   and bm is not None and bp is not None and (bm == bp or (bm and abs(bp / bm - 1) < 0.05)))
    if static_same and meta.get("materialized") == (sd.workloads[wid].get("main") or {}).get("materialized"):
        return 0.0, "static"
    # sample stage
    for env in ("key01", "key10"):
        for v in ("main", "pr"):
            xs = _vals(sd.runs(env), v, wid)
            if xs:
                ci_cost[env] += sum(xs) * (1 + 1 / len(xs))          # reps + warm-up
    m01, p01 = sd.env_medians("key01", wid)
    m10, p10 = sd.env_medians("key10", wid)
    two = est_ab_two_point(sd, wid)
    escalate = new
    if not new and m01 and m10 and p01 and p10:
        fs, fl = sd.env_rows["key01"], sd.env_rows["key10"]
        b_main = math.log(m10 / m01) / math.log(fl / fs)
        b_pr = math.log(p10 / p01) / math.log(fl / fs)
        r01, r10 = p01 / m01, p10 / m10
        h = sd.anchor(wid) or 0
        rel_two = (two / h) if (two is not None and h) else 0
        escalate = (b_pr - b_main > 0.15 or abs(math.log(r10 / r01)) > math.log(1.5)
                    or abs(rel_two) > 0.25)
    else:
        escalate = True
    if escalate:
        for v in ("main", "pr"):
            xs = _vals(sd.runs("prod"), v, wid, CI_REP)
            if xs:
                ci_cost["prod"] += 2 * sum(xs)                      # 1 rep + warm-up
        return est_ab_full_anchored(sd, wid), "full"
    return two, "sample"


def analyse():
    sds, env_rows = load()
    sec_per_cout, sec_per_byte = global_calibration(sds)
    nmodel = noise_model(sds)
    rows, wrows = [], []
    est_names = list(ESTIMATORS) + ["pr_vs_history", "hybrid"]
    levels = ["direct", "plus_1hop", "all_models", "all_with_consumers"]
    for sd in sds:
        dist = distances(sd)
        row = {"id": sd.id, "title": sd.rec["scenario"]["title"], "category": sd.rec["scenario"]["category"],
               "modified": sd.rec["changes"]["modified"], "n_workloads": len(sd.workloads),
               "detection": sd.rec["changes"].get("detection", "dbt_state")}
        tot_main = tot_delta = 0.0
        est_delta = {k: 0.0 for k in est_names}
        est_ok = {k: True for k in est_names}
        lvl_delta = {k: {lv: 0.0 for lv in levels} for k in ["truth", "ab_full_anchored"]}
        ci_cost = {"prod": 0.0, "key01": 0.0, "key10": 0.0}
        path_counts = {"static": 0, "sample": 0, "full": 0}
        est_ci = {k: 0.0 for k in est_names}      # lab-seconds executed by each strategy (Phase 11)
        one_run = 0.0                             # one production run of all affected workloads
        for wid, w in sd.workloads.items():
            meta = sd.meta(wid)
            runs = meta["runs_per_month"]
            m, p = sd.truth(wid)
            tot_main += runs * m
            tot_delta += runs * (p - m)
            per = {}
            for name, f in ESTIMATORS.items():
                if name == "static_cout":
                    v = f(sd, wid, sec_per_cout)
                else:
                    v = f(sd, wid)
                if v is None and name == "bytes_proxy":
                    bp = med(_vals(sd.runs("prod"), "pr", wid, CI_REP, "logical_bytes"))
                    v = bp * sec_per_byte if (bp and sec_per_byte) else None
                per[name] = v
            # PR-only run compared to production history
            pr_ci = med(_vals(sd.runs("prod"), "pr", wid, CI_REP))
            h = sd.anchor(wid) if sd.in_variant(wid, "main") else 0.0
            per["pr_vs_history"] = (pr_ci or 0.0) - (h or 0.0)
            per["hybrid"], path = hybrid(sd, wid, (sec_per_cout, sec_per_byte), ci_cost)
            path_counts[path] += 1
            one_run += m or p
            m_ci, p_ci = (med(_vals(sd.runs("prod"), v, wid, CI_REP)) or 0.0 for v in ("main", "pr"))
            for k in ("ab_full_abs", "ab_full_anchored"):
                est_ci[k] += 2 * (m_ci + p_ci)            # warm-up + measured run, both variants
            est_ci["pr_vs_history"] += 2 * p_ci
            for env in ("bern01", "key01", "key10", "recent90"):
                me, pe = (med(_vals(sd.runs(env), v, wid)) or 0.0 for v in ("main", "pr"))
                est_ci[f"ab_{env}"] += 4 * (me + pe)      # warm-up + 3 reps, both variants
            est_ci["ab_two_point"] = est_ci["ab_key01"] + est_ci["ab_key10"]
            for k in est_names:
                if per[k] is None:
                    est_ok[k] = False
                else:
                    est_delta[k] += runs * per[k]
            dw = dist.get(wid, 99)
            lvl_of = {"direct": dw == 0 and meta["kind"] == "model",
                      "plus_1hop": dw <= 1 and meta["kind"] == "model",
                      "all_models": meta["kind"] == "model",
                      "all_with_consumers": True}
            for lv, inc in lvl_of.items():
                if inc:
                    lvl_delta["truth"][lv] += runs * (p - m)
                    if per["ab_full_anchored"] is not None:
                        lvl_delta["ab_full_anchored"][lv] += runs * per["ab_full_anchored"]
            wrows.append({"scenario": sd.id, "workload": wid, "kind": meta["kind"],
                          "materialized_main": (w.get("main") or {}).get("materialized"),
                          "materialized_pr": (w.get("pr") or {}).get("materialized"),
                          "distance": dw, "runs_per_month": runs, "truth_main_s": m, "truth_pr_s": p,
                          "truth_paired_ratio": sd.truth_paired_ratio(wid), "anchor_s": sd.anchor(wid),
                          "sigma_log": sigma_for(nmodel, m or p),
                          **{f"est_{k}": v for k, v in per.items()}, "hybrid_path": path})
        rel = (tot_delta / tot_main) if tot_main > 0 else (math.inf if tot_delta > 0 else 0.0)
        # truth stability: the scenario's rel computed from each truth rep separately (paired by rep)
        per_rep = []
        for i in TRUTH_REPS:
            mm = pp = 0.0
            for wid in sd.workloads:
                runs_w = sd.meta(wid)["runs_per_month"]
                mv = _vals(sd.runs("prod"), "main", wid, [i])
                pv = _vals(sd.runs("prod"), "pr", wid, [i])
                mm += runs_w * (mv[0] if mv else 0.0)
                pp += runs_w * (pv[0] if pv else 0.0)
            per_rep.append((pp - mm) / mm if mm > 0 else (math.inf if pp > mm else 0.0))
        row["truth_rel_per_rep"] = per_rep
        row["truth_ambiguous"] = len({metrics.direction(x) for x in per_rep}) > 1
        est_ci["hybrid"] = sum(ci_cost.values())
        row["ci_cost_lab_s"] = est_ci
        row["one_prod_run_s"] = one_run
        row.update({"truth_main_monthly_s": tot_main, "truth_delta": tot_delta, "truth_rel": rel,
                    "hybrid_paths": path_counts, "hybrid_ci_cost_lab_s": ci_cost,
                    "levels": lvl_delta})
        for k in est_names:
            if est_ok[k]:
                row[f"{k}_delta"] = est_delta[k]
                row[f"{k}_rel"] = est_delta[k] / tot_main if tot_main > 0 else (math.inf if est_delta[k] > 0 else 0.0)
            else:
                row[f"{k}_delta"] = row[f"{k}_rel"] = None
        for lv in levels:
            row[f"lvl_{lv}_delta"] = lvl_delta["ab_full_anchored"][lv]
            row[f"lvl_{lv}_rel"] = (lvl_delta["ab_full_anchored"][lv] / tot_main) if tot_main > 0 else (
                math.inf if lvl_delta["ab_full_anchored"][lv] > 0 else 0.0)
        rows.append(row)
    scores = {k: metrics.score(rows, k) for k in est_names}
    stable = [r for r in rows if not r["truth_ambiguous"]]
    scores_stable = {k: metrics.score(stable, k) for k in est_names}
    # Economic view: impact relative to the whole production workload bill (all jobs + consumers),
    # so a 4x regression in a model that is 2% of a busy affected set still registers as material.
    econ = {}
    bpath = RESULTS / "baseline.json"
    if bpath.exists():
        base = json.loads(bpath.read_text(encoding="utf-8"))
        total = sum(v["runs_per_month"] * v["seconds"] for v in base.values())
        erows = []
        for r in rows:
            e = {"truth_rel": r["truth_delta"] / total, "truth_delta": r["truth_delta"]}
            for k in est_names:
                d = r.get(f"{k}_delta")
                e[f"{k}_rel"] = None if d is None else d / total
                e[f"{k}_delta"] = d
            erows.append(e)
            r["truth_rel_of_total_bill"] = e["truth_rel"]
        # materiality here = moves the total production bill by >= 1%
        saved = metrics.MATERIAL
        metrics.MATERIAL = 0.01
        econ = {k: metrics.score(erows, k) for k in est_names}
        metrics.MATERIAL = saved
        econ["_total_monthly_lab_s"] = total
    for k in est_names:
        runs_x = [r["ci_cost_lab_s"][k] / r["one_prod_run_s"] for r in rows if r["one_prod_run_s"]]
        share = [r["ci_cost_lab_s"][k] / r["truth_main_monthly_s"] for r in rows if r["truth_main_monthly_s"]]
        scores[k]["ci_cost_x_prod_run_median"] = st.median(runs_x) if runs_x else None
        scores[k]["ci_cost_x_prod_run_max"] = max(runs_x) if runs_x else None
        scores[k]["ci_cost_pct_of_monthly_median"] = 100 * st.median(share) if share else None
    scores.update({f"lvl_{lv}": metrics.score(rows, f"lvl_{lv}") for lv in levels})
    return {"rows": rows, "workloads": wrows, "scores": scores, "scores_stable_truth": scores_stable,
            "scores_economic_1pct_of_bill": econ,
            "n_ambiguous_truth": len(rows) - len(stable), "noise_model": nmodel,
            "calibration": {"sec_per_cout": sec_per_cout, "sec_per_byte": sec_per_byte},
            "env_rows": env_rows}


def fmt(x, pct=False, digits=2):
    if x is None:
        return "n/a"
    if isinstance(x, float) and math.isinf(x):
        return "new" if x > 0 else "-inf"
    return f"{x * 100:+.0f}%" if pct else f"{x:.{digits}f}"


def write_tables(res):
    TABLES.mkdir(parents=True, exist_ok=True)
    est = ["static_cout", "bytes_proxy", "ab_bern01", "ab_recent90", "ab_key01", "ab_key10",
           "ab_two_point", "hybrid", "pr_vs_history", "ab_full_anchored", "ab_full_abs"]
    lines = ["| scenario | truth | " + " | ".join(est) + " |",
             "|---|---|" + "---|" * len(est)]
    for r in res["rows"]:
        lines.append(f"| {r['id']} | {fmt(r['truth_rel'], True)} | "
                     + " | ".join(fmt(r.get(f'{k}_rel'), True) for k in est) + " |")
    (TABLES / "scenario_estimates.md").write_text("\n".join(lines) + "\n")
    keys = ["coverage", "direction_acc_material", "large_regression_recall", "large_regression_recall_strict",
            "false_warning_rate", "bucket_exact", "bucket_within_one", "median_abs_log_error_material",
            "within_2x_material", "spearman_monthly_delta", "ci_cost_x_prod_run_median",
            "ci_cost_pct_of_monthly_median"]
    lines = ["| estimator | " + " | ".join(keys) + " |", "|---|" + "---|" * len(keys)]
    for k in est + [f"lvl_{lv}" for lv in ["direct", "plus_1hop", "all_models", "all_with_consumers"]]:
        s = res["scores"][k]
        lines.append(f"| {k} | " + " | ".join(fmt(s.get(x)) for x in keys) + " |")
    n = res["scores"]["ab_full_anchored"]
    lines.append(f"\nn={n['n']} scenarios; material={n['n_material']}, immaterial={n['n_immaterial']}, "
                 f"large regressions={n['n_large']}")
    if "scores_cpu" in res:
        lines += ["", "Robustness: the same estimators scored against CPU-time (work) truth instead of latency:", "",
                  "| estimator | " + " | ".join(keys) + " |", "|---|" + "---|" * len(keys)]
        for k in est:
            s = res["scores_cpu"][k]
            lines.append(f"| {k} | " + " | ".join(fmt(s.get(x)) for x in keys) + " |")
        c = res["scores_cpu"]["ab_full_anchored"]
        lines.append(f"\n(CPU truth: material={c['n_material']}, immaterial={c['n_immaterial']}, large={c['n_large']})")
    (TABLES / "estimator_scores.md").write_text("\n".join(lines) + "\n")


def main():
    set_metric("cpu_s")                   # robustness: score everything against CPU-time truth too
    res_cpu = analyse()
    set_metric("latency_s")               # primary: elapsed engine time (dedicated-warehouse billing)
    res = analyse()
    res["scores_cpu"] = res_cpu["scores"]
    res["rows_cpu"] = [{k: v for k, v in r.items() if k.endswith("_rel") or k == "id"}
                       for r in res_cpu["rows"]]
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "analysis.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    write_tables(res)
    print((TABLES / "estimator_scores.md").read_text())
    print((TABLES / "scenario_estimates.md").read_text())


if __name__ == "__main__":
    main()
