"""Billing-rule tests. Each asserts a documented rule (docs/PLATFORM_FEASIBILITY.md §3)."""
import math

from costci.pools import (MONTH_S, TIB, Execution, bigquery_editions, bigquery_on_demand,
                          serverless_per_query, snowflake_warehouse)

RATE = dict(credits_per_hour=3600, price_per_credit=1.0)   # $1 per cluster-second, easy arithmetic


def test_snowflake_60s_minimum_per_resume():
    # a 10 s query on a suspended warehouse with auto-suspend 0 is billed 60 s
    r = snowflake_warehouse([Execution("q", 1000, 10)], auto_suspend_s=0, **RATE)
    assert r["dollars"] == 60


def test_snowflake_idle_tail_is_billed_until_auto_suspend():
    r = snowflake_warehouse([Execution("q", 1000, 100)], auto_suspend_s=600, **RATE)
    assert r["dollars"] == 700


def test_snowflake_queries_within_idle_tail_share_one_session():
    e = [Execution("a", 0, 100), Execution("b", 400, 100)]      # gap 300 < auto_suspend 600
    r = snowflake_warehouse(e, auto_suspend_s=600, **RATE)
    assert r["dollars"] == 500 + 600


def test_snowflake_marginal_cost_of_doubling_a_short_query_is_small():
    base = snowflake_warehouse([Execution("q", 0, 10)], auto_suspend_s=60, **RATE)["dollars"]
    doubled = snowflake_warehouse([Execution("q", 0, 20)], auto_suspend_s=60, **RATE)["dollars"]
    assert (doubled - base) / base < 0.2          # +100% runtime, ~+14% bill


def test_snowflake_always_on_marginal_cost_is_zero_without_scale_out():
    a = snowflake_warehouse([Execution("q", 0, 10)], auto_suspend_s=None, **RATE)["dollars"]
    b = snowflake_warehouse([Execution("q", 0, 1000)], auto_suspend_s=None, **RATE)["dollars"]
    assert a == b == MONTH_S


def test_snowflake_multicluster_starts_second_cluster_above_concurrency():
    execs = [Execution(f"q{i}", 1000, 100) for i in range(9)]    # 9 concurrent > 8 per cluster
    one = snowflake_warehouse(execs[:8], auto_suspend_s=0, max_clusters=2, **RATE)["dollars"]
    two = snowflake_warehouse(execs, auto_suspend_s=0, max_clusters=2, **RATE)["dollars"]
    assert two > one


def test_bigquery_on_demand_bytes_and_minimum():
    r = bigquery_on_demand([Execution("q", 0, 1, bytes=TIB)], price_per_tib=6.25)
    assert math.isclose(r["dollars"], 6.25)
    tiny = bigquery_on_demand([Execution("q", 0, 1, bytes=1)], price_per_tib=6.25)
    assert tiny["bytes_billed"] == 10 * 1024 ** 2


def test_bigquery_editions_baseline_absorbs_small_demand():
    small = bigquery_editions([Execution("q", 0, 100, slot_s=100 * 50)], baseline_slots=100)
    bigger = bigquery_editions([Execution("q", 0, 100, slot_s=100 * 90)], baseline_slots=100)
    assert small["dollars"] == bigger["dollars"]                 # both under 100 baseline slots


def test_bigquery_editions_autoscale_rounds_to_50_and_holds_60s():
    r = bigquery_editions([Execution("q", 0, 10, slot_s=10 * 10)], baseline_slots=0)
    # 10 slots needed -> 50 allocated, held >= 60 s
    assert r["autoscale_slot_seconds"] == 50 * 60


def test_serverless_per_query_is_linear():
    r = serverless_per_query([Execution("q", 0, 3600)], price_per_unit_hour=2.0)
    assert r["dollars"] == 2.0


def test_bigquery_editions_has_no_phantom_autoscale_from_float_residue():
    # This seeded input leaves a +3.3e-13 residue in the cumulative slot demand after every job has
    # ended; without the fix, ceil() billed a phantom 50-slot step for the rest of the month.
    import random
    rng = random.Random(1)
    execs = [Execution(f"q{i}", rng.uniform(0, 5000), rng.uniform(1, 40)) for i in range(3000)]
    for e in execs:
        e.slot_s = e.duration_s * 25 * rng.uniform(0.3, 3.7)
    r = bigquery_editions(execs, baseline_slots=0, max_slots=800)
    busy_window = 5000 + 40 + 60 + 1
    assert r["autoscale_slot_seconds"] <= 800 * busy_window
