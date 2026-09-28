"""Capacity pools: turn a month of workload executions into billed dollars.

The point of this module is that the dollar impact of a change is a property of the capacity pool
(warehouse / reservation / serverless), not of the query. Each pool replays a month-long timeline
of executions under documented billing rules; the marginal cost of a change is
    bill(timeline with PR durations) - bill(timeline with MAIN durations).

Rule provenance (see docs/PLATFORM_FEASIBILITY.md):
  snowflake_warehouse   DOCUMENTED: per-second billing, 60 s minimum per resume, idle billed until
                        AUTO_SUSPEND, multi-cluster rate = size rate x running clusters.
                        ASSUMED: queries do not slow each other down; extra clusters start when
                        concurrency exceeds 8 per cluster and stop after 120 s idle (Snowflake
                        publishes no numeric Standard-policy timing).
  bigquery_on_demand    DOCUMENTED: $ per TiB of bytes billed; ASSUMED: 10 MB minimum per query.
  bigquery_editions     DOCUMENTED: baseline slots billed continuously; autoscaled slots billed
                        per second with a 1-minute minimum, in 50-slot increments.
                        ASSUMED: slot demand of a query = slot-seconds / duration.
  serverless_per_query  per-second consumption with no idle/minimum (Databricks serverless jobs,
                        Snowflake QUERY_ATTRIBUTION-style accounting): the "attributed" view.
Everything is deterministic given the timeline.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

MONTH_S = 30 * 24 * 3600
TIB = 1024 ** 4


@dataclass
class Execution:
    workload: str
    start_s: float
    duration_s: float
    bytes: float = 0.0          # logical bytes processed (for byte-priced pools)
    slot_s: float = 0.0         # slot-seconds (CPU-seconds) for slot-priced pools


def _merge_sessions(intervals: list[tuple[float, float]], idle_tail: float) -> list[tuple[float, float]]:
    """Merge busy intervals into warehouse sessions (a session ends idle_tail after the last query)."""
    if not intervals:
        return []
    intervals = sorted(intervals)
    out = []
    cur_s, cur_e = intervals[0][0], intervals[0][1] + idle_tail
    for s, e in intervals[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e + idle_tail)
        else:
            out.append((cur_s, cur_e))
            cur_s, cur_e = s, e + idle_tail
    out.append((cur_s, cur_e))
    return out


def snowflake_warehouse(execs: list[Execution], credits_per_hour: float, price_per_credit: float,
                        auto_suspend_s: float | None = 600, min_billing_s: float = 60,
                        max_clusters: int = 1, concurrency_per_cluster: int = 8,
                        scale_down_idle_s: float = 120, **_) -> dict:
    rate = credits_per_hour / 3600 * price_per_credit          # $ per cluster-second
    if auto_suspend_s is None:                                   # never suspends: first cluster always on
        base_seconds = MONTH_S
    else:
        tail = max(auto_suspend_s, 0)
        sessions = _merge_sessions([(e.start_s, e.start_s + e.duration_s) for e in execs], tail)
        base_seconds = sum(max(min_billing_s, min(e, MONTH_S) - s) for s, e in sessions)
    extra_seconds = 0.0
    if max_clusters > 1 and execs:
        # concurrency profile at 1-second resolution; cluster k (k>=2) runs while
        # concurrency > (k-1)*concurrency_per_cluster, plus scale-down idle, 60 s minimum per start
        conc = np.zeros(MONTH_S + 1, dtype=np.int32)
        for e in execs:
            a = int(e.start_s)
            b = min(MONTH_S, int(math.ceil(e.start_s + e.duration_s)))
            conc[a] += 1
            conc[max(b, a + 1)] -= 1
        conc = np.cumsum(conc)[:MONTH_S]
        for k in range(2, max_clusters + 1):
            busy = np.flatnonzero(conc > (k - 1) * concurrency_per_cluster)
            if busy.size == 0:
                break
            runs = np.split(busy, np.flatnonzero(np.diff(busy) > 1) + 1)
            sessions = _merge_sessions([(float(r[0]), float(r[-1] + 1)) for r in runs], scale_down_idle_s)
            extra_seconds += sum(max(min_billing_s, e - s) for s, e in sessions)
    busy_seconds = sum(e.duration_s for e in execs)
    return {"dollars": (base_seconds + extra_seconds) * rate,
            "billed_cluster_seconds": base_seconds + extra_seconds,
            "busy_seconds": busy_seconds}


def bigquery_on_demand(execs: list[Execution], price_per_tib: float = 6.25,
                       min_bytes_per_query: float = 10 * 1024 ** 2, **_) -> dict:
    billed = sum(max(e.bytes, min_bytes_per_query) for e in execs)
    return {"dollars": billed / TIB * price_per_tib, "bytes_billed": billed,
            "busy_seconds": sum(e.duration_s for e in execs)}


def bigquery_editions(execs: list[Execution], price_per_slot_hour: float = 0.06,
                      baseline_slots: int = 100, max_slots: int = 400, increment: int = 50,
                      min_scale_s: int = 60, **_) -> dict:
    demand = np.zeros(MONTH_S + 1, dtype=np.float64)
    for e in execs:
        if e.duration_s <= 0:
            continue
        slots = e.slot_s / e.duration_s
        a = int(e.start_s)
        b = min(MONTH_S, int(math.ceil(e.start_s + e.duration_s)))
        demand[a] += slots
        demand[max(b, a + 1)] -= slots
    demand = np.cumsum(demand)[:MONTH_S]
    need = np.clip(demand - baseline_slots, 0, max_slots - baseline_slots)
    auto = np.ceil(need / increment) * increment
    # hold each scale-up for at least min_scale_s (running max over a trailing window)
    if auto.any():
        held = auto.copy()
        idx = np.flatnonzero(np.diff(np.concatenate([[0.0], auto])) > 0)
        for i in idx:
            j = min(MONTH_S, i + min_scale_s)
            held[i:j] = np.maximum(held[i:j], auto[i])
        auto = held
    slot_seconds = baseline_slots * MONTH_S + auto.sum()
    return {"dollars": slot_seconds / 3600 * price_per_slot_hour,
            "autoscale_slot_seconds": float(auto.sum()),
            "busy_seconds": sum(e.duration_s for e in execs)}


def serverless_per_query(execs: list[Execution], price_per_unit_hour: float, **_) -> dict:
    s = sum(e.duration_s for e in execs)
    return {"dollars": s / 3600 * price_per_unit_hour, "busy_seconds": s}


BILLING = {
    "snowflake_warehouse": snowflake_warehouse,
    "bigquery_on_demand": bigquery_on_demand,
    "bigquery_editions": bigquery_editions,
    "serverless_per_query": serverless_per_query,
}


def bill(pool: dict, execs: list[Execution]) -> dict:
    return BILLING[pool["kind"]](execs, **{k: v for k, v in pool.items() if k != "kind"})
