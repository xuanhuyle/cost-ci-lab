"""Recurring-cost layer: per-run durations -> a month of executions per pool -> dollars.

A month timeline is generated from the production context (job schedules, BI consumer volumes).
Durations are lab seconds x time_scale; bytes are lab logical bytes x data_scale. Unaffected
workloads use their measured production baseline (results/baseline.json), so a change on a
shared pool is billed against the real background load of that pool.

Two ways to price a change are compared:
  attributed  delta_seconds x runs x unit rate   (what per-query attribution would say)
  marginal    bill(month with PR) - bill(month with MAIN) under the pool's billing rules
"""
from __future__ import annotations

import copy
import random

from .pools import MONTH_S, Execution, bill

DAY = 86400

# Pool configurations used for the portability matrix. Prices/rules: docs/PLATFORM_FEASIBILITY.md.
# DOCUMENTED: Snowflake credits/hour by size, $3.00/credit Enterprise AWS us-east-1 on-demand, 60 s
# minimum; BigQuery $6.25/TiB on-demand, $0.06 Enterprise slot-hour PAYG, 50-slot autoscale steps.
# ASSUMED: Databricks $/DBU (list prices render dynamically; not captured from a primary source),
# slot demand per lab thread, cluster scale-down timing.
POOL_MATRIX = {
    "snowflake_dedicated": {
        "transform_wh": {"kind": "snowflake_warehouse", "credits_per_hour": 4, "price_per_credit": 3.0,
                         "auto_suspend_s": 60},
        "bi_wh": {"kind": "snowflake_warehouse", "credits_per_hour": 2, "price_per_credit": 3.0,
                  "auto_suspend_s": 300, "max_clusters": 2},
    },
    "snowflake_always_on_bi": {
        "transform_wh": {"kind": "snowflake_warehouse", "credits_per_hour": 4, "price_per_credit": 3.0,
                         "auto_suspend_s": 60},
        "bi_wh": {"kind": "snowflake_warehouse", "credits_per_hour": 2, "price_per_credit": 3.0,
                  "auto_suspend_s": None, "max_clusters": 2},
    },
    "attributed_per_second": {       # QUERY_ATTRIBUTION-style: busy seconds x rate, no idle/minimums
        "transform_wh": {"kind": "serverless_per_query", "price_per_unit_hour": 12.0},
        "bi_wh": {"kind": "serverless_per_query", "price_per_unit_hour": 6.0},
    },
    "bigquery_on_demand": {
        "transform_wh": {"kind": "bigquery_on_demand", "price_per_tib": 6.25},
        "bi_wh": {"kind": "bigquery_on_demand", "price_per_tib": 6.25},
    },
    "bigquery_editions": {
        "transform_wh": {"kind": "bigquery_editions", "price_per_slot_hour": 0.06, "baseline_slots": 0,
                         "max_slots": 800},
        "bi_wh": {"kind": "bigquery_editions", "price_per_slot_hour": 0.06, "baseline_slots": 100,
                  "max_slots": 400},
    },
    "databricks_sql_serverless": {   # Medium = 24 DBU/h (Azure doc); $0.70/DBU ASSUMED; 10 min auto-stop
        "transform_wh": {"kind": "snowflake_warehouse", "credits_per_hour": 24, "price_per_credit": 0.70,
                         "auto_suspend_s": 600, "min_billing_s": 0},
        "bi_wh": {"kind": "snowflake_warehouse", "credits_per_hour": 12, "price_per_credit": 0.70,
                  "auto_suspend_s": 600, "min_billing_s": 0, "max_clusters": 2},
    },
}

SLOTS_PER_LAB_THREAD = 25     # ASSUMED: a 4-thread lab engine ~ 100 BigQuery slots


def _consumer_starts(cid: str, runs: int, business_hours=(8, 20)) -> list[float]:
    rng = random.Random(f"consumer:{cid}")
    h0, h1 = business_hours
    out = []
    for _ in range(int(runs)):
        day = rng.randrange(30)
        out.append(day * DAY + rng.uniform(h0 * 3600, h1 * 3600))
    return sorted(out)


def month_executions(ctx: dict, per_run: dict[str, dict]) -> dict[str, list[Execution]]:
    """per_run: workload id -> {"seconds": lab seconds, "bytes": lab bytes, "cpu": lab cpu seconds}.

    Returns pool name -> executions for one 30-day month.
    """
    ts, ds = ctx["time_scale"], ctx["data_scale"]
    by_pool: dict[str, list[Execution]] = {}

    def ex(wid, start):
        u = per_run[wid]
        return Execution(wid, start, u["seconds"] * ts, u.get("bytes", 0.0) * ds,
                         u.get("cpu", u["seconds"]) * ts * SLOTS_PER_LAB_THREAD)

    jobs = {j["id"]: j for j in ctx["jobs"]}
    models_by_job: dict[str, list[str]] = {}
    for wid, u in per_run.items():
        if wid.startswith("model:"):
            models_by_job.setdefault(u["job"], []).append(wid)
    for job_id, wids in models_by_job.items():
        job = jobs[job_id]
        pool = job["pool"]
        runs = int(job["runs_per_month"])
        period = MONTH_S / runs
        for i in range(runs):
            t = i * period + job.get("start_minute", 0) * 60
            for wid in sorted(wids, key=lambda w: per_run[w].get("order", 0)):
                e = ex(wid, t)
                by_pool.setdefault(pool, []).append(e)
                t += e.duration_s
    for c in ctx["consumers"]:
        wid = f"consumer:{c['id']}"
        if wid not in per_run:
            continue
        for t in _consumer_starts(c["id"], c["runs_per_month"]):
            by_pool.setdefault(c["pool"], []).append(ex(wid, t))
    return by_pool


def monthly_bill(ctx: dict, pools: dict, per_run: dict) -> dict:
    execs = month_executions(ctx, per_run)
    out = {}
    for name, cfg in pools.items():
        out[name] = bill(cfg, execs.get(name, []))
    out["total"] = {"dollars": sum(v["dollars"] for v in out.values())}
    return out


def delta_dollars(ctx: dict, pools: dict, baseline: dict, main: dict, pr: dict) -> dict:
    """Marginal monthly $ of replacing MAIN per-run usage with PR per-run usage.

    baseline: every production workload (unaffected ones keep these values)
    main/pr:  per-run usage for affected workloads (absent from pr => removed; new in pr => added)
    """
    m = copy.deepcopy(baseline)
    m.update(main)
    p = copy.deepcopy(baseline)
    for wid in main:
        if wid not in pr:
            p.pop(wid, None)
    p.update(pr)
    bm = monthly_bill(ctx, pools, m)
    bp = monthly_bill(ctx, pools, p)
    return {"main": bm["total"]["dollars"], "pr": bp["total"]["dollars"],
            "delta": bp["total"]["dollars"] - bm["total"]["dollars"],
            "by_pool": {k: bp[k]["dollars"] - bm[k]["dollars"] for k in pools}}
