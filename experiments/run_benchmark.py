"""Experiment 1 driver: measure every benchmark scenario (MAIN vs PR) in every environment.

For each scenario:
  1. change detection + workload mapping + compilation with real dbt (costci.scenario.prepare)
  2. prod environment (TPC-H SF2, 4 threads): warm-up + PROD_REPS interleaved reps.
     The analysis assigns reps: rep 1 -> "CI full-clone A/B" estimate, reps 2-4 -> MAIN
     "production history", reps 5-8 -> ground truth. Disjoint reps keep noise independent.
  3. each CI sample environment: warm-up + SAMPLE_REPS interleaved reps.
Writes results/bench/<scenario>.json (compact, committed).

Usage: python -m experiments.run_benchmark [--only s01_widen_date_filter ...]
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict

from costci import dbtops
from costci.measure import ensure_prod_schema, measure_env
from costci.paths import RESULTS
from costci.scenario import Workspace, load_scenarios, prepare

SAMPLE_ENVS = ["bern01", "key01", "key10", "recent90"]
PROD_REPS = 8
SAMPLE_REPS = 3


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--detection", choices=["dbt_state", "union"], default="dbt_state",
                    help="union = dbt state:modified plus rendered-SQL diff (results/bench_union)")
    args = ap.parse_args()
    out_dir = RESULTS / ("bench" if args.detection == "dbt_state" else "bench_union")
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    ws = Workspace()
    built = ensure_prod_schema(ws, ["prod", *SAMPLE_ENVS])
    print(f"workspace ready in {time.perf_counter() - t0:.1f}s; prod schemas rebuilt: {list(built)}",
          flush=True)

    for sc in load_scenarios(args.only):
        path = out_dir / f"{sc.id}.json"
        if args.skip_existing and path.exists():
            continue
        t_start = time.perf_counter()
        dbtops.TIMINGS.clear()
        prep = prepare(ws, sc, detection=args.detection)
        t_prep = time.perf_counter() - t_start
        record = {
            "scenario": {k: v for k, v in asdict(sc).items() if k != "dir"},
            "changes": asdict(prep.changes),
            "context": prep.context,
            "workloads": {v: [asdict(w) for w in wl] for v, wl in prep.plans.items()},
            "timing": {"prepare_s": t_prep, "dbt_calls": dbtops.TIMINGS[:]},
            "envs": {},
        }
        t_env = {}
        for env, reps in [("prod", PROD_REPS)] + [(e, SAMPLE_REPS) for e in SAMPLE_ENVS]:
            t1 = time.perf_counter()
            record["envs"][env] = measure_env(env, prep.plans, reps, explain=(env == "prod"))
            t_env[env] = time.perf_counter() - t1
        record["timing"]["env_s"] = t_env
        path.write_text(json.dumps(record, indent=1, default=str))
        print(f"{sc.id}: prepare {t_prep:.1f}s, measure "
              + ", ".join(f"{k} {v:.1f}s" for k, v in t_env.items())
              + f" | modified={prep.changes.modified} +={prep.changes.modified_plus} "
              f"consumers={prep.changes.consumers}", flush=True)


if __name__ == "__main__":
    main()
