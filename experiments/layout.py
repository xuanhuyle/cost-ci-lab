"""Experiment 8: how much does a change's *true* cost depend on physical layout?

Re-measures pruning- and window-sensitive scenarios on `prodfine`: identical rows to `prod`, but
8,192-row row groups (~1.7 days of line items each, vs ~26 days by default at SF2). A CI strategy
that rebuilds or samples data cannot reproduce the production layout; a zero-copy clone does.
MEASURED (local engine). Writes results/layout.json.

Prerequisite: python -m costci.data --only prodfine
"""
from __future__ import annotations

import json
import statistics as st

from costci.measure import ensure_prod_schema, measure_env
from costci.paths import RESULTS
from costci.scenario import Workspace, load_scenarios, prepare

SCENARIOS = ["s01_widen_date_filter", "s02_remove_partition_pruning", "s03_expand_incremental_window",
             "s04_incremental_to_table", "s13_select_fewer_columns", "s24_var_default_change"]
REPS = 6


def summarise(res, bench_rec=None):
    out = {}
    for v in ("main", "pr"):
        tot = None
        for wid, runs in res["runs"][v].items():
            vals = [r["latency_s"] for r in runs]
            tot = vals if tot is None else [a + b for a, b in zip(tot, vals)]
        out[v] = st.median(tot) if tot else 0.0
    out["ratio"] = out["pr"] / out["main"] if out["main"] else None
    return out


def main():
    ws = Workspace()
    ensure_prod_schema(ws, ["prodfine"])
    results = {}
    for sc in load_scenarios(SCENARIOS):
        prep = prepare(ws, sc)
        fine = summarise(measure_env("prodfine", prep.plans, REPS))
        coarse = summarise(measure_env("prod", prep.plans, REPS))
        results[sc.id] = {"coarse_default_rowgroups": coarse, "fine_8192_rowgroups": fine}
        print(sc.id, "coarse ratio", round(coarse["ratio"] or 0, 3), "fine ratio", round(fine["ratio"] or 0, 3),
              flush=True)
    (RESULTS / "layout.json").write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
