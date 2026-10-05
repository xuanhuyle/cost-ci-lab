"""Phase A (pre-merge CI prediction) and Phase B (shadow-production truth) for one PR each.

Walks the usable corpus in merge order. For PR i:

  Phase A  - copy the production database to a CI database;
             build the affected node set A from the MAIN tree and from the PR tree, interleaved,
             R repetitions each, in the CI regime (small engine, cold, isolated);
           - write and hash an immutable prediction artifact.

  Phase B  - only after the prediction file exists and its hash is recorded;
             in the production regime (larger engine, warm, with background load) on the
             production database: build A from MAIN (production baseline for those nodes), then
             deploy - build A from PR. R repetitions each.
           - production therefore advances along main's real history, PR by PR.

The estimator is frozen before the first holdout PR (F2) and nothing here reads holdout truth
before writing the corresponding prediction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics as st
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402

from costci.public_pr import DbtProject, ensure_worktree, harvest, rmtree, write_profile  # noqa: E402

CLONE = ROOT / "work" / "corpus" / "tuva-core"
PUB = ROOT / "work" / "pub"
WT_MAIN, WT_PR = PUB / "wt_main", PUB / "wt_pr"
PKG_CACHE = PUB / "pkgcache"
# DuckDB names the catalog after the database file's stem, and a view's stored definition
# embeds that catalog name ("prod"."core"."patient"). The baseline build created 178 views, so
# the CI copy must keep the file NAME and change only the directory; otherwise every view in the
# clone fails to bind. (The counterfactual clone has to present the same database identity as
# production - a real constraint on the zero-copy-clone design, not a lab artefact.)
DB_PROD = PUB / "db" / "prod.duckdb"
DB_CI = PUB / "db_ci" / "prod.duckdb"
# DuckDB takes an exclusive file lock: a read-only handle in this process prevents the dbt
# subprocess from opening the same file read-write at all (verified). The production-regime
# background load therefore runs against its own copy of the same data, so it competes for CPU,
# memory and IO - which is what slows a concurrent query down - without taking the lock.
DB_BG = PUB / "db_bg" / "prod.duckdb"
PROF_CI, PROF_PROD = PUB / "profiles_ci", PUB / "profiles_prod"
RES = ROOT / "results" / "public_pr"
PROJECT_SUBDIR = "integration_tests"
DBT_VARS = {"synthetic_data_size": "large"}

# --- regimes (docs/SHADOW_PRODUCTION_DESIGN.md §1), fixed before any holdout truth -------------
# Sized for a 16 GB laptop (CLAUDE.md). The CI/production gap is what matters, not the absolute
# values: production gets 2x the threads and 3x the memory ceiling.
CI = {"threads": 2, "memory": "2GB", "warm": False, "background": False}
PROD = {"threads": 4, "memory": "6GB", "warm": True, "background": True}
BG_MEMORY = "1GB"      # the background connection must be capped too: DuckDB otherwise defaults
                       # it to ~80% of system RAM, which OOM-killed an earlier run
REPS = 3                      # protocol amendment 2026-10-05, before any holdout truth
DEV_N, HOLD_N = 10, 20        # protocol amendment 2026-10-05, before any holdout truth

# Node-level exclusion, decided from the baseline build before any PR was measured.
# data_quality__testing_summary reads "prod"."main"."dbt_tests", a relation produced by an
# on-run-end hook that does not exist on DuckDB, so the node fails on MAIN at the baseline
# commit independently of any PR. It is a leaf (child_map is empty), so removing it cannot
# change any other node's cost. results/public_pr/baseline_build.json records the failure.
BROKEN_NODES = {"data_quality__testing_summary"}

def _incremental_models() -> set[str]:
    """Models whose repeated build is NOT idempotent, so repetitions on one database would
    contaminate each other.

    In this corpus the only incremental models are the Elementary observability artefacts
    (dbt_models, dbt_run_results, data_monitoring_metrics, ...), which are not descendants of any
    Tuva transformation. Everything else is table (709), view (192) or ephemeral (55) and is
    rebuilt by CREATE OR REPLACE from the same inputs, so repeated A/B runs on one CI database
    are safe. Any PR whose affected set does intersect this list is flagged in its record rather
    than being silently measured.
    """
    try:
        man = json.loads((PUB / "wt_prod" / "integration_tests" / "target"
                          / "manifest.json").read_text(encoding="utf-8"))
        return {n["name"] for n in man["nodes"].values()
                if n.get("resource_type") == "model"
                and n["config"].get("materialized") == "incremental"}
    except Exception:
        return set()


INCREMENTAL = _incremental_models()


def _full_job_seconds() -> float:
    try:
        b = json.loads((RES / "baseline_build.json").read_text(encoding="utf-8"))
        return sum(float(n["execution_time"]) for n in b["nodes"]
                   if (n.get("unique_id") or "").startswith("model.")
                   and n.get("execution_time") is not None)
    except Exception:
        return 0.0


FULL_JOB_SECONDS = _full_job_seconds()

BACKGROUND_SQL = [
    "select count(*) from core.medical_claim",
    "select data_source, count(*) from core.eligibility group by 1",
    "select count(distinct person_id) from core.patient",
]


class BackgroundLoad:
    """A concurrent read workload on a separate copy of the same data: production contention
    (E-039 measured -18%..+58% from exactly this). It cannot share the measured database file,
    see the note on DB_BG above."""

    def __init__(self, enabled: bool):
        self.enabled, self._stop, self._t = enabled, threading.Event(), None
        self.queries = 0
        self.error = ""

    def __enter__(self):
        if self.enabled:
            if not DB_BG.exists():
                DB_BG.parent.mkdir(parents=True, exist_ok=True)
                checkpoint(DB_PROD)
                shutil.copy2(DB_PROD, DB_BG)
            self._t = threading.Thread(target=self._loop, daemon=True)
            self._t.start()
        return self

    def _loop(self):
        try:
            con = duckdb.connect(str(DB_BG), read_only=True)
            con.execute("SET threads=1")
            con.execute(f"SET memory_limit='{BG_MEMORY}'")
        except Exception as e:                                   # noqa: BLE001
            self.error = str(e)[:200]
            return
        i = 0
        while not self._stop.is_set():
            try:
                con.execute(BACKGROUND_SQL[i % len(BACKGROUND_SQL)]).fetchall()
                self.queries += 1
            except Exception:
                pass
            i += 1
        try:
            con.close()
        except Exception:
            pass

    def __exit__(self, *a):
        self._stop.set()
        if self._t:
            self._t.join(timeout=10)
        return False


def prime(db: Path) -> None:
    """Warm the OS/page cache the way a recurring production job leaves it.

    The connection is opened and closed before any dbt subprocess starts, because DuckDB's file
    lock is exclusive.
    """
    try:
        con = duckdb.connect(str(db), read_only=True)
        con.execute("SET memory_limit='1GB'")
        for q in BACKGROUND_SQL:
            try:
                con.execute(q).fetchall()
            except Exception:
                pass
        con.close()
    except Exception:
        pass


def checkpoint(db: Path) -> None:
    """Fold the WAL into the database file so a plain file copy is a consistent snapshot."""
    try:
        con = duckdb.connect(str(db), config={"memory_limit": "1GB"})
        con.execute("CHECKPOINT")
        con.close()
    except Exception:
        pass


def copy_db(src: Path, dst: Path) -> float:
    t0 = time.perf_counter()
    checkpoint(src)
    dst.unlink(missing_ok=True)
    Path(str(dst) + ".wal").unlink(missing_ok=True)
    shutil.copy2(src, dst)
    wal = Path(str(src) + ".wal")
    if wal.exists() and wal.stat().st_size > 0:
        shutil.copy2(wal, str(dst) + ".wal")
    return time.perf_counter() - t0


def build_once(project: DbtProject, nodes: list[str], cap_s: int) -> dict:
    if not nodes:                       # an empty --select would build the whole project
        return {"ok": False, "wall_s": 0.0, "nodes": {}, "total_s": 0.0, "failed": [],
                "error": "empty node set", "n_selected": 0, "sel_chars": 0}
    sel = " ".join(nodes)
    res = project.run(["run", "--select", *nodes, "--vars", json.dumps(DBT_VARS)],
                      timeout=cap_s)
    times, failed = harvest(project)
    return {"ok": res.ok, "wall_s": round(res.seconds, 2), "nodes": times,
            "total_s": round(sum(times.values()), 4), "failed": failed,
            "error": res.error[-1500:] if not res.ok else "", "n_selected": len(nodes),
            "sel_chars": len(sel)}


def regime_project(wt: Path, regime: dict, db: Path, profiles: Path) -> DbtProject:
    return DbtProject(wt, PROJECT_SUBDIR, profiles, PKG_CACHE, db,
                      threads=regime["threads"], memory_limit=regime["memory"])


def measure_pair(rec: dict, regime: dict, db: Path, profiles: Path, cap_s: int,
                 label: str) -> dict:
    """Interleaved MAIN/PR repetitions of the affected node set in one regime."""
    nodes = rec["affected"]
    runs = []
    # worktrees and packages are set up once per PR per regime, not per repetition
    projs = {}
    for variant, wt, sha in (("main", WT_MAIN, rec["base_sha"]), ("pr", WT_PR, rec["head_sha"])):
        ensure_worktree(CLONE, wt, sha)
        proj = regime_project(wt, regime, db, profiles)
        proj.deps()
        projs[variant] = proj
    bg = BackgroundLoad(regime["background"])
    if regime["warm"]:
        prime(db)
    t_phase = time.perf_counter()
    with bg:
        for rep in range(REPS):
            for variant in ("main", "pr"):
                elapsed = time.perf_counter() - t_phase
                remaining = cap_s - elapsed
                if remaining <= 0:
                    # The cap is per PHASE (protocol §7), not per dbt invocation. Running out of
                    # budget is an ABSTAIN outcome, which is a result, not an exclusion.
                    return {"runs": runs, "ok": False, "abstain": True,
                            "reason": "phase compute cap exceeded",
                            "phase_elapsed_s": round(elapsed, 1),
                            "background_queries": bg.queries, "background_error": bg.error}
                proj = projs[variant]
                r = build_once(proj, nodes, int(remaining))
                r.update(variant=variant, rep=rep, regime=label)
                runs.append(r)
                if not r["ok"]:
                    timed_out = r["error"] == "TIMEOUT"
                    return {"runs": runs, "ok": False, "abstain": timed_out,
                            "reason": "phase compute cap exceeded" if timed_out else "build failed",
                            "phase_elapsed_s": round(time.perf_counter() - t_phase, 1),
                            "background_queries": bg.queries, "background_error": bg.error}
    return {"runs": runs, "ok": True, "abstain": False,
            "phase_elapsed_s": round(time.perf_counter() - t_phase, 1),
            "background_queries": bg.queries, "background_error": bg.error}


def advance_production(rec: dict, cap_s: int) -> dict:
    """Deploy the PR state into the shadow production database without measuring it.

    Used when a PR could not be measured. Production must still move to `C`, otherwise every
    later PR would be evaluated against a base state that never existed on main.
    """
    ensure_worktree(CLONE, WT_PR, rec["head_sha"])
    proj = regime_project(WT_PR, PROD, DB_PROD, PROF_PROD)
    proj.deps()
    r = build_once(proj, rec["affected"], cap_s)
    return {"ok": r["ok"], "wall_s": r["wall_s"], "error": r["error"][-800:]}


def summarise(runs: list[dict]) -> dict:
    out = {}
    for v in ("main", "pr"):
        tots = [r["total_s"] for r in runs if r["variant"] == v and r["ok"]]
        out[v] = {"n": len(tots), "median_s": st.median(tots) if tots else None,
                  "values": tots,
                  "cv": (st.pstdev(tots) / st.mean(tots)) if len(tots) > 1 and st.mean(tots) else 0.0}
    m, p = out["main"]["median_s"], out["pr"]["median_s"]
    out["delta_s"] = (p - m) if (m is not None and p is not None) else None
    out["rel"] = ((p - m) / m) if (m not in (None, 0) and p is not None) else None
    return out


def grade(summary: dict) -> str:
    """Confidence from measured run-to-run spread, as in E5: does the interval stay inside one
    direction class?"""
    rel, m, p = summary["rel"], summary["main"], summary["pr"]
    if rel is None:
        return "NONE"
    cv = max(m["cv"], p["cv"])
    if m["n"] < 2 or p["n"] < 2:
        return "LOW"
    half = 1.28 * cv * (2 ** 0.5)        # 80% interval on the ratio, propagated
    lo, hi = rel - half, rel + half
    same = (lo >= 0.10 and hi >= 0.10) or (lo <= -0.10 and hi <= -0.10) or (-0.10 < lo and hi < 0.10)
    return "HIGH" if same else "MEDIUM"


def git_sha() -> str:
    import subprocess
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def record_freeze(point: str, detail: dict) -> None:
    """F2/F3/F4 of docs/PUBLIC_CORPUS_PROTOCOL.md §10, appended as they happen."""
    path = RES / "freeze.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if point in data:
        return
    data[point] = {"git_sha": git_sha(), "at": time.strftime("%Y-%m-%dT%H:%M:%S"), **detail}
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"   [freeze {point}] {data[point]['git_sha'][:8]}", flush=True)


def freeze(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload, indent=1, sort_keys=True).encode()
    path.write_bytes(blob)
    return hashlib.sha256(blob).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cap-minutes", type=int, default=45)
    ap.add_argument("--only", type=int, nargs="*", help="specific PR numbers")
    ap.add_argument("--trial", action="store_true",
                    help="smoke test: separate worktrees, a throwaway copy of the production "
                         "database and a separate output file, so the real timeline is untouched")
    args = ap.parse_args()
    cap_s = args.cap_minutes * 60

    global WT_MAIN, WT_PR, DB_PROD, DB_CI, DB_BG, PROF_CI, PROF_PROD, RES_OUT
    RES_OUT = RES / "measurements.json"
    if args.trial:
        WT_MAIN, WT_PR = PUB / "wt_t_main", PUB / "wt_t_pr"
        DB_PROD = PUB / "db_trial_prod" / "prod.duckdb"
        DB_CI = PUB / "db_trial_ci" / "prod.duckdb"
        DB_BG = PUB / "db_trial_bg" / "prod.duckdb"
        PROF_CI, PROF_PROD = PUB / "profiles_t_ci", PUB / "profiles_t_prod"
        RES_OUT = RES / "measurements_trial.json"
        DB_PROD.parent.mkdir(parents=True, exist_ok=True)
        DB_CI.parent.mkdir(parents=True, exist_ok=True)
        if not DB_PROD.exists():
            print("trial: copying the production database (throwaway)", flush=True)
            shutil.copy2(PUB / "db" / "prod.duckdb", DB_PROD)

    recs = json.loads((RES / "reconstruction.json").read_text(encoding="utf-8"))
    usable = [r for r in recs if r.get("executable")]
    for i, r in enumerate(usable):
        r["split"] = "development" if i < DEV_N else ("holdout" if i < DEV_N + HOLD_N
                                                      else "reserve")

    DB_CI.parent.mkdir(parents=True, exist_ok=True)
    write_profile(PROF_CI, DB_CI, CI["threads"], CI["memory"])
    write_profile(PROF_PROD, DB_PROD, PROD["threads"], PROD["memory"])
    (RES / "holdout_predictions").mkdir(parents=True, exist_ok=True)

    out_path = RES_OUT
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else []
    seen = {d["pr"] for d in done}
    n = 0
    for rec in usable:
        if rec["pr"] in seen:
            continue
        if args.only and rec["pr"] not in args.only:
            continue
        if args.limit and n >= args.limit:
            break
        n += 1
        print(f"\n=== PR #{rec['pr']} [{rec['split']}] {rec['merged_at'][:10]} "
              f"affected={rec['n_affected']}", flush=True)
        dropped = [n for n in rec["affected"] if n in BROKEN_NODES]
        if dropped:
            rec["affected"] = [n for n in rec["affected"] if n not in BROKEN_NODES]
            rec["n_affected"] = len(rec["affected"])
        non_idempotent = sorted(set(rec["affected"]) & INCREMENTAL)
        row = {"pr": rec["pr"], "split": rec["split"], "merged_at": rec["merged_at"],
               "nodes_dropped_broken_on_main": dropped,
               "non_idempotent_affected_nodes": non_idempotent,
               "base_sha": rec["base_sha"], "head_sha": rec["head_sha"],
               "subject": rec["subject"], "n_affected": rec["n_affected"],
               "affected": rec["affected"], "touched": rec["touched"]}

        if rec["split"] == "holdout" and not args.trial:
            record_freeze("F2_estimator_frozen",
                          {"note": "estimator and harness frozen before the first holdout "
                                   "prediction", "first_holdout_pr": rec["pr"]})
        # ---- Phase A: pre-merge CI prediction
        t0 = time.perf_counter()
        row["ci_db_copy_s"] = round(copy_db(DB_PROD, DB_CI), 1)
        a = measure_pair(rec, CI, DB_CI, PROF_CI, cap_s, "ci")
        row["phase_a"] = a
        row["phase_a_wall_s"] = round(time.perf_counter() - t0, 1)
        if not a["ok"]:
            row["outcome"] = "CI_ABSTAIN_TOO_EXPENSIVE" if a.get("abstain") else "CI_BUILD_FAILED"
            row["detail"] = next((r["error"] for r in a["runs"] if not r["ok"]), "")[-1200:]
            row["deploy_only"] = advance_production(rec, cap_s)
            done.append(row)
            out_path.write_text(json.dumps(done, indent=1), encoding="utf-8")
            print(f"   CI build failed; production advanced "
                  f"ok={row['deploy_only']['ok']}", flush=True)
            continue
        pred = summarise(a["runs"])
        pred["grade"] = grade(pred)
        pred["analysis_wall_s"] = row["phase_a_wall_s"]
        pred["analysis_engine_s"] = sum(r["total_s"] for r in a["runs"])
        # production-run equivalents: engine seconds spent analysing / one production run of A
        base_run = pred["main"]["median_s"] or 0.0
        # k_affected is fixed by the protocol (REPS x 2 variants) and is reported only for
        # comparability with E-037. k_job is the decision-relevant one: what fraction of one
        # full production job run the check costs, which varies with blast radius.
        pred["k_production_runs"] = (pred["analysis_engine_s"] / base_run) if base_run else None
        pred["k_full_job_runs"] = ((pred["analysis_engine_s"] / FULL_JOB_SECONDS)
                                   if FULL_JOB_SECONDS else None)
        row["prediction"] = pred
        row["prediction_sha256"] = freeze(
            RES / ("trial_predictions" if args.trial else "holdout_predictions")
            / f"pr_{rec['pr']}.json",
            {"pr": rec["pr"], "split": rec["split"], "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "affected": rec["affected"], "prediction": pred})
        print(f"   prediction rel={pred['rel']} grade={pred['grade']} "
              f"k={pred['k_production_runs']}", flush=True)
        if rec["split"] == "holdout" and not args.trial:
            record_freeze("F3_first_holdout_prediction",
                          {"pr": rec["pr"], "prediction_sha256": row["prediction_sha256"]})

        # ---- Phase B: shadow-production truth (prediction is already on disk and hashed)
        t1 = time.perf_counter()
        b = measure_pair(rec, PROD, DB_PROD, PROF_PROD, cap_s, "production")
        row["phase_b"] = b
        row["phase_b_wall_s"] = round(time.perf_counter() - t1, 1)
        if not b["ok"]:
            row["outcome"] = ("PROD_ABSTAIN_TOO_EXPENSIVE" if b.get("abstain")
                              else "PROD_BUILD_FAILED")
            row["detail"] = next((r["error"] for r in b["runs"] if not r["ok"]), "")[-1200:]
            row["deploy_only"] = advance_production(rec, cap_s)
        else:
            truth = summarise(b["runs"])
            row["truth"] = truth
            row["outcome"] = "OK"
            print(f"   truth      rel={truth['rel']} (bg queries={b['background_queries']})",
                  flush=True)
        done.append(row)
        out_path.write_text(json.dumps(done, indent=1), encoding="utf-8")

    print(f"\nmeasured {n} PRs -> {out_path}")


if __name__ == "__main__":
    main()
