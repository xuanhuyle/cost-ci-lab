"""Measure every production workload of the MAIN project (the "production history" of the whole
pool), so economic replays can bill a change against the real background load of its pool.

Runs all models as they run in production (incremental models in incremental mode) plus every BI
consumer, in the prod environment, warm-up + REPS interleaved-free reps. Writes
results/baseline.json. Must not run concurrently with run_benchmark (shares the compile catalog
and would distort timings).
"""
from __future__ import annotations

import json
import statistics as st

from costci import dbtops
from costci.measure import measure_env
from costci.paths import RESULTS
from costci.scenario import (Workload, Workspace, _topo, job_for, load_context,
                             resolve_consumer)

REPS = 5


def main() -> None:
    ws = Workspace()
    ctx = load_context()
    models = ws.models(ws.main_manifest)
    order = _topo(list(models), models)
    compiled = dbtops.compile_nodes(ws.main, ws.profiles, order, "main", ws.state)
    plan = []
    for n in order:
        node = compiled[n]
        job = job_for(models[n], ctx)
        plan.append(Workload(id=f"model:{n}", kind="model", name=n, sql=node["compiled_code"],
                             materialized=node["config"]["materialized"],
                             unique_key=node["config"].get("unique_key"), job=job["id"],
                             runs_per_month=job["runs_per_month"], pool=job["pool"]))
    for c in ctx["consumers"]:
        plan.append(Workload(id=f"consumer:{c['id']}", kind="consumer", name=c["id"],
                             sql=resolve_consumer(c["sql"], set(order), "ci_main"),
                             materialized=None, unique_key=None, job=None,
                             runs_per_month=c["runs_per_month"], pool=c["pool"]))
    # measure_env interleaves MAIN/PR; measure the same plan as both variants and pool the reps
    res = measure_env("prod", {"main": plan, "pr": []}, REPS)
    out = {}
    for i, w in enumerate(plan):
        runs = res["runs"]["main"][w.id]
        out[w.id] = {
            "seconds": st.median(r["latency_s"] for r in runs),
            "cpu": st.median(r["cpu_s"] for r in runs),
            "bytes": st.median(r["logical_bytes"] for r in runs),
            "cv": st.pstdev([r["latency_s"] for r in runs]) / max(st.mean(r["latency_s"] for r in runs), 1e-9),
            "job": w.job, "pool": w.pool, "runs_per_month": w.runs_per_month, "order": i,
            "materialized": w.materialized, "kind": w.kind,
        }
    (RESULTS / "baseline.json").write_text(json.dumps(out, indent=1))
    for wid, v in out.items():
        print(f"{wid:40s} {v['seconds']*1000:9.1f} ms  cv {v['cv']:.2f}  x{v['runs_per_month']}/mo")


if __name__ == "__main__":
    main()
