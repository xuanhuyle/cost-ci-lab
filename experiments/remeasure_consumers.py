"""Protocol fix for millisecond-scale consumer queries (applied to E1 records in place).

Finding that motivated it (see RESULTS.md): BI consumer queries take ~2-150 ms but run up to
60,000 times a month, so their per-run noise dominates the monthly delta. One execution per rep
made both the CI estimate (s18: -7% vs truth +81%) and the truth itself (s21, a cosmetic change:
+26%) unreliable. Any real CI protocol would repeat cheap statements; it costs milliseconds.

New protocol for consumer workloads only: models of each variant are built once (unmeasured), then
every rep of a consumer = median of K executions, interleaved MAIN/PR with alternating order, same
rep counts and rep roles as run_benchmark (prod: warm-up + 8; samples: warm-up + 3). The consumer
entries of results/bench*/<id>.json are replaced and the record is annotated.
"""
from __future__ import annotations

import json
import statistics as st

from costci import dbtops
from costci.execute import Session
from costci.paths import RESULTS
from costci.scenario import Workspace, load_scenarios, prepare

K = 5
REPS = {"prod": 8, "bern01": 3, "key01": 3, "key10": 3, "recent90": 3}


def build_models(s: Session, plans) -> None:
    for v, plan in plans.items():
        schema = dbtops.SCHEMAS[v]
        s.reset_schema(schema)
        for w in plan:
            if w.kind == "model":
                s.build(w.name, schema, w.sql, w.materialized, w.unique_key)


def measure_consumers(env: str, plans) -> dict:
    s = Session(env)
    build_models(s, plans)
    consumers = {v: [w for w in plans[v] if w.kind == "consumer"] for v in plans}
    runs = {v: {w.id: [] for w in consumers[v]} for v in plans}
    for rep in range(REPS[env] + 1):
        order = ["main", "pr"] if rep % 2 == 0 else ["pr", "main"]
        for v in order:
            for w in consumers[v]:
                us = [s.query(w.sql).as_dict() for _ in range(K)]
                if rep == 0:
                    continue
                agg = {k: st.median(u[k] for u in us) for k in us[0] if isinstance(us[0][k], (int, float))}
                agg["executions"] = K
                runs[v][w.id].append(agg)
    s.close()
    return runs


def main():
    ws = Workspace()
    for folder in ("bench", "bench_union"):
        for path in sorted((RESULTS / folder).glob("s*.json")):
            rec = json.loads(path.read_text(encoding="utf-8"))
            if not any(w["kind"] == "consumer" for v in rec["workloads"].values() for w in v):
                continue
            if rec.get("protocol", {}).get("consumers") == f"median of {K} executions per rep":
                continue
            sc = next(s for s in load_scenarios([rec["scenario"]["id"]]))
            prep = prepare(ws, sc, detection=rec["changes"].get("detection", "dbt_state"))
            for env in REPS:
                new = measure_consumers(env, prep.plans)
                for v, by_w in new.items():
                    for wid, reps in by_w.items():
                        rec["envs"][env]["runs"][v][wid] = reps
            rec.setdefault("protocol", {})["consumers"] = f"median of {K} executions per rep"
            path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
            print(folder, rec["scenario"]["id"], "consumers re-measured", flush=True)


if __name__ == "__main__":
    main()
