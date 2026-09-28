"""Estimators of the per-run resource delta of each affected workload, and ground truth.

Inputs are the measurement records written by experiments/run_benchmark.py. Every estimator only
uses information that would be available pre-merge in CI:
  * prod env rep 1            -> one CI run on a full production clone ("ab_full")
  * prod env reps 2-4 (MAIN)  -> production history of the current code ("anchor")
  * sample envs               -> CI runs on cheaper data
  * EXPLAIN plans             -> static information (no execution)
Ground truth = median of prod reps 5-8 for each variant (disjoint from everything above).

The unit is "workload-seconds per run" (engine latency at 4 threads). Converting to money is
the job of costci.pools / costci.economics.
"""
from __future__ import annotations

import math
import statistics as st

CI_REP = [0]
HIST_REPS = [1, 2, 3]
TRUTH_REPS = [4, 5, 6, 7]
SAMPLE_ENVS = ["bern01", "key01", "key10", "recent90"]
# fraction of production fact rows present in each sample env (lineitem rows / prod lineitem rows)
METRIC = "latency_s"


def _vals(runs: dict, variant: str, wid: str, reps: list[int] | None = None, metric=METRIC):
    xs = runs.get(variant, {}).get(wid)
    if not xs:
        return None
    if reps is not None:
        xs = [xs[i] for i in reps if i < len(xs)]
    return [x[metric] for x in xs]


def med(xs):
    return st.median(xs) if xs else None


class ScenarioData:
    """Convenience accessors over one results/bench/<id>.json record."""

    def __init__(self, rec: dict, env_rows: dict):
        self.rec = rec
        self.id = rec["scenario"]["id"]
        self.workloads = {}
        for v in ("main", "pr"):
            for w in rec["workloads"][v]:
                self.workloads.setdefault(w["id"], {})[v] = w
        self.env_rows = env_rows

    def runs(self, env):
        return self.rec["envs"][env]["runs"]

    def in_variant(self, wid, v):
        return v in self.workloads[wid]

    def meta(self, wid):
        w = self.workloads[wid]
        return w.get("pr") or w.get("main")

    # ---- truth and anchor
    def truth(self, wid, metric=METRIC):
        r = self.runs("prod")
        m = med(_vals(r, "main", wid, TRUTH_REPS, metric)) or 0.0
        p = med(_vals(r, "pr", wid, TRUTH_REPS, metric)) or 0.0
        return m, p

    def truth_paired_ratio(self, wid, metric=METRIC):
        r = self.runs("prod")
        m = _vals(r, "main", wid, TRUTH_REPS, metric)
        p = _vals(r, "pr", wid, TRUTH_REPS, metric)
        if not m or not p:
            return None
        return med([b / a for a, b in zip(m, p) if a > 0])

    def anchor(self, wid, metric=METRIC):
        return med(_vals(self.runs("prod"), "main", wid, HIST_REPS, metric))

    def hist_spread(self, wid, metric=METRIC):
        xs = _vals(self.runs("prod"), "main", wid, HIST_REPS, metric)
        if not xs or len(xs) < 2:
            return None
        return (max(xs) - min(xs)) / max(med(xs), 1e-9)

    # ---- measurement accessors for estimators
    def env_medians(self, env, wid, reps=None, metric=METRIC):
        r = self.runs(env)
        return med(_vals(r, "main", wid, reps, metric)), med(_vals(r, "pr", wid, reps, metric))

    def explain_cout(self, wid):
        ex = self.rec["envs"]["prod"].get("explain", {})
        out = []
        for v in ("main", "pr"):
            ops = ex.get(v, {}).get(wid)
            out.append(None if ops is None else sum(o["ec"] for o in ops))
        return out

    def explain_shape(self, wid):
        ex = self.rec["envs"]["prod"].get("explain", {})
        shapes = []
        for v in ("main", "pr"):
            ops = ex.get(v, {}).get(wid)
            shapes.append(None if ops is None else sorted(o["op"] for o in ops))
        return shapes


# --------------------------------------------------------------------------- estimators
# Each returns (delta_seconds_per_run, info) for one workload, or None if it cannot estimate.

def _anchored(sd: ScenarioData, wid, ratio, absolute_pr=None):
    """Apply a PR/MAIN ratio to the production history of MAIN. New workloads need an absolute."""
    if sd.in_variant(wid, "main"):
        h = sd.anchor(wid)
        if h is None or ratio is None or not math.isfinite(ratio):
            return None
        return h * (ratio - 1.0)
    return absolute_pr          # new workload: no anchor exists


def est_ab_full_abs(sd, wid):
    m, p = sd.env_medians("prod", wid, CI_REP)
    return (p or 0.0) - (m or 0.0)


def est_ab_full_anchored(sd, wid):
    m, p = sd.env_medians("prod", wid, CI_REP)
    ratio = (p / m) if (m and p is not None) else None
    return _anchored(sd, wid, ratio, absolute_pr=p)


def est_ab_sample(env):
    def f(sd, wid):
        m, p = sd.env_medians(env, wid)
        ratio = (p / m) if (m and p is not None) else None
        frac = sd.env_rows[env]
        absolute = (p / frac) if p is not None else None       # linear scale-up for new workloads
        return _anchored(sd, wid, ratio, absolute_pr=absolute)
    f.__name__ = f"ab_{env}"
    return f


def _two_point(d_small, d_large, f_small, f_large):
    """Power-law extrapolation of a duration to full scale from two sample fractions."""
    if not d_small or not d_large or d_small <= 0 or d_large <= 0:
        return d_large / f_large if d_large else None
    b = math.log(d_large / d_small) / math.log(f_large / f_small)
    b = min(max(b, 0.0), 2.5)                                    # guard against noise
    return d_large * (1.0 / f_large) ** b


def est_ab_two_point(sd, wid):
    fs, fl = sd.env_rows["key01"], sd.env_rows["key10"]
    m01, p01 = sd.env_medians("key01", wid)
    m10, p10 = sd.env_medians("key10", wid)
    pm = _two_point(m01, m10, fs, fl) if sd.in_variant(wid, "main") else None
    pp = _two_point(p01, p10, fs, fl)
    if pp is None:
        return None
    ratio = (pp / pm) if pm else None
    return _anchored(sd, wid, ratio, absolute_pr=pp)


def est_static_cout(sd, wid, sec_per_cout=None):
    cm, cp = sd.explain_cout(wid)
    meta = sd.meta(wid)
    if meta["kind"] == "model" and meta.get("materialized") == "view":
        # building a view costs ~nothing; static view of a view build is "no work"
        if sd.in_variant(wid, "main") and sd.workloads[wid]["main"].get("materialized") != "view":
            return -sd.anchor(wid)
        return 0.0
    if cp is None:
        return None
    if cm is None or cm == 0:
        return cp * sec_per_cout if (sec_per_cout and cm is None) else None
    return _anchored(sd, wid, cp / cm, absolute_pr=None)


def est_bytes_proxy(sd, wid):
    m, p = sd.env_medians("prod", wid, CI_REP, metric="logical_bytes")
    if m is None and p is not None and sd.in_variant(wid, "main") is False:
        return None
    if not m:
        return None if p else 0.0
    return _anchored(sd, wid, (p or 0.0) / m)


ESTIMATORS = {
    "static_cout": est_static_cout,
    "bytes_proxy": est_bytes_proxy,
    "ab_full_abs": est_ab_full_abs,
    "ab_full_anchored": est_ab_full_anchored,
    "ab_bern01": est_ab_sample("bern01"),
    "ab_key01": est_ab_sample("key01"),
    "ab_key10": est_ab_sample("key10"),
    "ab_recent90": est_ab_sample("recent90"),
    "ab_two_point": est_ab_two_point,
}
