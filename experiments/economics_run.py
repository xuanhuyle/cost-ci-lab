"""Experiment 2: from resource deltas to recurring dollars under different capacity pools.

For every scenario and every pool configuration in costci.economics.POOL_MATRIX:
  truth_marginal   bill(month with measured PR usage) - bill(month with measured MAIN usage),
                   unaffected workloads at their measured production baseline
  naive_attributed sum over affected workloads of runs x delta(unit) x unit price
                   (what per-query attribution / "cost per run x frequency" would report)
  est_marginal     pool replay with *estimated* PR usage (history anchor x CI full-clone ratio)
The billing rules are DOCUMENTED; their application to a synthetic month is SIMULATED, and the
lab->production unit conversion (time_scale, data_scale, slots per thread) is ASSUMED.
Writes results/economics.json and results/tables/economics.md.
"""
from __future__ import annotations

import copy
import json
import math

from costci.economics import POOL_MATRIX, SLOTS_PER_LAB_THREAD, delta_dollars
from costci.estimators import CI_REP, HIST_REPS, TRUTH_REPS, ScenarioData, _vals, med
from costci.paths import DATA, RESULTS

TIB = 1024 ** 4


def usage(sd: ScenarioData, wid: str, variant: str, reps) -> dict | None:
    r = sd.runs("prod")
    s = med(_vals(r, variant, wid, reps, "latency_s"))
    if s is None:
        return None
    return {"seconds": s, "cpu": med(_vals(r, variant, wid, reps, "cpu_s")),
            "bytes": med(_vals(r, variant, wid, reps, "logical_bytes"))}


def naive(pool: dict, ctx: dict, deltas: list[tuple[float, dict, dict]]) -> float:
    kind = pool["kind"]
    tot = 0.0
    for runs, m, p in deltas:
        if kind == "snowflake_warehouse":
            rate = pool["credits_per_hour"] * pool["price_per_credit"] / 3600
            tot += runs * (p["seconds"] - m["seconds"]) * ctx["time_scale"] * rate
        elif kind == "serverless_per_query":
            tot += runs * (p["seconds"] - m["seconds"]) * ctx["time_scale"] * pool["price_per_unit_hour"] / 3600
        elif kind == "bigquery_on_demand":
            tot += runs * (p["bytes"] - m["bytes"]) * ctx["data_scale"] / TIB * pool["price_per_tib"]
        elif kind == "bigquery_editions":
            tot += (runs * (p["cpu"] - m["cpu"]) * ctx["time_scale"] * SLOTS_PER_LAB_THREAD
                    * pool["price_per_slot_hour"] / 3600)
    return tot


def main():
    baseline = json.loads((RESULTS / "baseline.json").read_text(encoding="utf-8"))
    envs = json.loads((DATA / "environments.json").read_text())
    env_rows = {e: envs[e]["rows"]["lineitem"] / envs["prod"]["rows"]["lineitem"]
                for e in envs if not e.startswith("_")}
    out = []
    for path in sorted((RESULTS / "bench").glob("s*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        sd = ScenarioData(rec, env_rows)
        ctx = rec["context"]
        base_run = {k: dict(v) for k, v in baseline.items()}
        main_t, pr_t, main_e, pr_e, deltas_t = {}, {}, {}, {}, []
        max_order = max(v["order"] for v in base_run.values())
        for wid, w in sd.workloads.items():
            meta = sd.meta(wid)
            info = {"job": meta.get("job"), "order": base_run.get(wid, {}).get("order", max_order + 1)}
            mt, pt = usage(sd, wid, "main", TRUTH_REPS), usage(sd, wid, "pr", TRUTH_REPS)
            if mt:
                main_t[wid] = {**mt, **info}
            if pt:
                pr_t[wid] = {**pt, **info}
            deltas_t.append((meta["runs_per_month"], mt or {"seconds": 0, "cpu": 0, "bytes": 0},
                             pt or {"seconds": 0, "cpu": 0, "bytes": 0}))
            # estimate: anchor (history) x CI full-clone ratio, per metric
            ma, pc, mc = usage(sd, wid, "main", HIST_REPS), usage(sd, wid, "pr", CI_REP), usage(sd, wid, "main", CI_REP)
            if ma:
                main_e[wid] = {**ma, **info}
            if pc:
                if ma and mc:
                    pr_e[wid] = {k: (ma[k] * pc[k] / mc[k] if mc[k] else pc[k]) for k in ("seconds", "cpu", "bytes")}
                else:
                    pr_e[wid] = dict(pc)
                pr_e[wid].update(info)
        row = {"id": sd.id, "category": rec["scenario"]["category"], "pools": {}}
        own = {"own_context": ctx["pools"]}
        for name, pools in {**own, **POOL_MATRIX}.items():
            t = delta_dollars(ctx, pools, base_run, main_t, pr_t)
            e = delta_dollars(ctx, pools, base_run, main_e, pr_e)
            nv = sum(naive(pools[p], ctx, [d for d, wid in zip(deltas_t, sd.workloads)
                                          if sd.meta(wid)["pool"] == p]) for p in pools)
            row["pools"][name] = {"truth_marginal": t["delta"], "truth_main_bill": t["main"],
                                  "est_marginal": e["delta"], "naive_attributed": nv,
                                  "truth_by_pool": t["by_pool"]}
        out.append(row)
        print(sd.id, {k: round(v["truth_marginal"], 1) for k, v in row["pools"].items()}, flush=True)
    (RESULTS / "economics.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    write_table(out)


def write_table(out):
    names = ["own_context"] + list(POOL_MATRIX)
    lines = ["Monthly $ impact (truth marginal / naive attributed / estimated marginal). "
             "Lab units scaled by ASSUMED time_scale=data_scale=100.", "",
             "| scenario | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for r in out:
        cells = []
        for n in names:
            p = r["pools"][n]
            cells.append(f"{p['truth_marginal']:+.0f} / {p['naive_attributed']:+.0f} / {p['est_marginal']:+.0f}")
        lines.append(f"| {r['id']} | " + " | ".join(cells) + " |")
    (RESULTS / "tables").mkdir(parents=True, exist_ok=True)
    (RESULTS / "tables" / "economics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
