"""Experiment 3: does a CI measurement transfer to production *conditions*?

For a subset of scenarios, re-measure MAIN vs PR in the prod environment under conditions that a
CI run typically does not share with production:
  size      CI on a smaller "warehouse" (1 thread) vs production (4 threads)
  load      production under concurrent background load on the same engine (shared CPU + memory
            limit, like a shared warehouse) vs an isolated CI run
  cold      a single run on a freshly opened database (no warm-up) vs the warmed protocol
All numbers are MEASURED on the local engine; transfer to Snowflake is INFERRED only.
Writes results/transfer.json.
"""
from __future__ import annotations

import json
import statistics as st
import threading
import time

from costci import dbtops
from costci.execute import Session
from costci.measure import measure_env
from costci.paths import RESULTS
from costci.scenario import Workspace, load_scenarios, prepare

SCENARIOS = ["s01_widen_date_filter", "s05_many_to_many_join", "s04_incremental_to_table",
             "s08_expensive_window", "s22_sort_for_determinism",
             "s09_repeated_scans"]
REPS = 3
BACKGROUND_SQL = ("SELECT l_partkey, count(*), sum(l_extendedprice), max(l_comment) "
                  "FROM lab.raw.lineitem GROUP BY 1 ORDER BY 2 DESC LIMIT 10")


def totals(res):
    """Median per-rep total latency per variant, and median paired ratio."""
    out = {}
    for v in ("main", "pr"):
        per_rep = None
        for runs in res["runs"][v].values():
            vals = [r["latency_s"] for r in runs]
            per_rep = vals if per_rep is None else [a + b for a, b in zip(per_rep, vals)]
        out[v] = per_rep or []
    ratios = [p / m for m, p in zip(out["main"], out["pr"]) if m > 0]
    return {"main_s": st.median(out["main"]) if out["main"] else None,
            "pr_s": st.median(out["pr"]) if out["pr"] else None,
            "ratio": st.median(ratios) if ratios else None,
            "ratios": ratios}


class Background:
    def __init__(self, env: str, n_threads: int = 2):
        self.stop = threading.Event()
        self.env = env
        self.n = n_threads
        self.threads = []
        self.count = 0
        self.errors: list[str] = []

    def _loop(self):
        # Same process + same file => same DuckDB instance: background queries share the engine's
        # thread pool and memory limit with the measured queries, like tenants of one warehouse.
        s = Session(self.env)
        while not self.stop.is_set():
            try:
                s.con.execute(BACKGROUND_SQL).fetchall()
                self.count += 1
            except Exception as e:          # e.g. out-of-memory under contention: record, continue
                self.errors.append(str(e)[:200])
                time.sleep(0.5)
        s.close()

    def __enter__(self):
        for _ in range(self.n):
            t = threading.Thread(target=self._loop, daemon=True)
            t.start()
            self.threads.append(t)
        time.sleep(2)
        return self

    def __exit__(self, *a):
        self.stop.set()
        for t in self.threads:
            t.join()


def cold_single(plans):
    """Fresh connection, no warm-up: one MAIN run then one PR run (a naive CI protocol)."""
    s = Session("prod")
    out = {}
    for v in ("main", "pr"):
        schema = dbtops.SCHEMAS[v]
        s.reset_schema(schema)
        tot = 0.0
        for w in plans[v]:
            u = (s.build(w.name, schema, w.sql, w.materialized, w.unique_key) if w.kind == "model"
                 else s.query(w.sql))
            tot += u.latency_s
        out[v] = tot
    s.close()
    return {"main_s": out["main"], "pr_s": out["pr"],
            "ratio": out["pr"] / out["main"] if out["main"] else None}


def main():
    ws = Workspace()
    results = {}
    for sc in load_scenarios(SCENARIOS):
        prep = prepare(ws, sc)
        r = {}
        t0 = time.perf_counter()

        def attempt(key, fn):
            try:
                r[key] = fn()
            except Exception as e:           # a failure (e.g. OOM under load) is itself a result
                r[key] = {"error": str(e)[:300], "ratio": None}

        attempt("cold_single", lambda: cold_single(prep.plans))
        attempt("prod_4t", lambda: totals(measure_env("prod", prep.plans, REPS, threads=4)))
        attempt("ci_1t", lambda: totals(measure_env("prod", prep.plans, REPS, threads=1)))
        with Background("prod") as bg:
            attempt("prod_4t_loaded", lambda: totals(measure_env("prod", prep.plans, REPS, threads=4)))
            r["background_queries"] = bg.count
            r["background_errors"] = bg.errors[:5]
        r["seconds"] = time.perf_counter() - t0
        results[sc.id] = r
        print(sc.id, {k: (round(v["ratio"], 3) if isinstance(v, dict) and v.get("ratio") else v)
                      for k, v in r.items()}, flush=True)
    (RESULTS / "transfer.json").write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
