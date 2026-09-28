"""Experiment 4: downstream cost propagation (Phase 9).

    delta(PR) = direct changed-workload delta + downstream workload deltas

Strategies compared against measured truth (from results/analysis.json):
  direct        execute only the modified models (state:modified)
  plus_1hop     execute modified models and their direct children
  all_models    execute everything dbt selects with state:modified+ (Slim CI default)
  all+consumers additionally execute the BI/consumer queries of the affected relations
  elasticity    execute only the modified models, measure how their output row count changed,
                and scale each descendant's production cost by that row ratio (no execution)
For the elasticity strategy this script measures output rows of the modified models (MAIN vs PR)
in the prod environment and in the key10 sample. Writes results/downstream.json.
"""
from __future__ import annotations

import json
import math
import statistics as st

from costci import dbtops
from costci.execute import Session
from costci.paths import RESULTS
from costci.scenario import Workspace, load_scenarios, prepare


def output_rows(env: str, plans, modified: set[str]) -> dict:
    s = Session(env)
    out = {}
    for v in ("main", "pr"):
        schema = dbtops.SCHEMAS[v]
        s.reset_schema(schema)
        rows = {}
        for w in plans[v]:
            if w.kind != "model" or w.name not in modified:
                continue
            s.build(w.name, schema, w.sql, w.materialized, w.unique_key)
            rows[w.name] = s.con.execute(f'SELECT count(*) FROM "lab"."{schema}"."{w.name}"').fetchone()[0]
        out[v] = rows
    s.close()
    return out


def main():
    analysis = json.loads((RESULTS / "analysis.json").read_text(encoding="utf-8"))
    wl = {}
    for w in analysis["workloads"]:
        wl.setdefault(w["scenario"], []).append(w)
    ws = Workspace()
    res = {}
    for sc in load_scenarios():
        rows = wl.get(sc.id, [])
        if not any(w["distance"] > 0 for w in rows):
            continue                                    # no downstream workloads
        prep = prepare(ws, sc)
        modified = set(prep.changes.modified)
        counts = {env: output_rows(env, prep.plans, modified) for env in ("prod", "key10")}
        entry = {"counts": counts, "strategies": {}}
        base = sum(w["runs_per_month"] * w["truth_main_s"] for w in rows)
        truth = sum(w["runs_per_month"] * (w["truth_pr_s"] - w["truth_main_s"]) for w in rows)
        entry["truth_rel"] = truth / base if base else None
        for env in ("prod", "key10"):
            c = counts[env]
            ratios = [c["pr"][m] / c["main"][m] for m in c["main"] if m in c["pr"] and c["main"][m]]
            row_ratio = math.exp(st.mean(math.log(r) for r in ratios)) if ratios else 1.0
            direct = sum(w["runs_per_month"] * (w["est_ab_full_anchored"] or 0)
                         for w in rows if w["distance"] == 0)
            prop = sum(w["runs_per_month"] * (w["anchor_s"] or 0) * (row_ratio - 1)
                       for w in rows if w["distance"] > 0 and w["anchor_s"])
            entry["strategies"][f"elasticity_{env}"] = {"row_ratio": row_ratio,
                                                        "rel": (direct + prop) / base if base else None}
        exec_cost = {}
        for lv, pred in (("direct", lambda w: w["distance"] == 0 and w["kind"] == "model"),
                         ("plus_1hop", lambda w: w["distance"] <= 1 and w["kind"] == "model"),
                         ("all_models", lambda w: w["kind"] == "model"),
                         ("all_with_consumers", lambda w: True)):
            sel = [w for w in rows if pred(w)]
            est = sum(w["runs_per_month"] * (w["est_ab_full_anchored"] or 0) for w in sel)
            entry["strategies"][lv] = {"rel": est / base if base else None,
                                       "ci_exec_lab_s": sum(w["truth_main_s"] + w["truth_pr_s"] for w in sel)}
            exec_cost[lv] = entry["strategies"][lv]["ci_exec_lab_s"]
        direct_cost = exec_cost["direct"]
        for env in ("prod", "key10"):
            entry["strategies"][f"elasticity_{env}"]["ci_exec_lab_s"] = direct_cost
        res[sc.id] = entry
        print(sc.id, "truth", _p(entry["truth_rel"]),
              {k: _p(v["rel"]) for k, v in entry["strategies"].items()}, flush=True)
    (RESULTS / "downstream.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


def _p(x):
    return "n/a" if x is None else f"{x * 100:+.0f}%"


if __name__ == "__main__":
    main()
