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
DB_PROD = PUB / "db" / "prod.duckdb"
DB_CI = PUB / "db" / "ci.duckdb"
PROF_CI, PROF_PROD = PUB / "profiles_ci", PUB / "profiles_prod"
RES = ROOT / "results" / "public_pr"
PROJECT_SUBDIR = "integration_tests"
DBT_VARS = {"synthetic_data_size": "large"}

# --- regimes (docs/SHADOW_PRODUCTION_DESIGN.md §1), fixed before any holdout truth -------------
CI = {"threads": 2, "memory": "3GB", "warm": False, "background": False}
PROD = {"threads": 4, "memory": "8GB", "warm": True, "background": True}
REPS = 2

BACKGROUND_SQL = [
    "select count(*) from core.medical_claim",
    "select data_source, count(*) from core.eligibility group by 1",
    "select count(distinct person_id) from core.patient",
]


class BackgroundLoad:
    """A second connection replaying a fixed read workload: production contention (E-039)."""

    def __init__(self, db: Path, enabled: bool):
        self.db, self.enabled, self._stop, self._t = db, enabled, threading.Event(), None
        self.queries = 0

    def __enter__(self):
        if self.enabled:
            self._t = threading.Thread(target=self._loop, daemon=True)
            self._t.start()
        return self

    def _loop(self):
        try:
            con = duckdb.connect(str(self.db), read_only=True)
            con.execute("SET threads=1")
        except Exception:
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
    """Warm the buffer manager the way a recurring production job leaves it."""
    try:
        con = duckdb.connect(str(db), read_only=True)
        for q in BACKGROUND_SQL:
            try:
                con.execute(q).fetchall()
            except Exception:
                pass
        con.close()
    except Exception:
        pass


def copy_db(src: Path, dst: Path) -> float:
    t0 = time.perf_counter()
    rmtree(dst) if dst.is_dir() else dst.unlink(missing_ok=True)
    Path(str(dst) + ".wal").unlink(missing_ok=True)
    shutil.copy2(src, dst)
    return time.perf_counter() - t0


def build_once(project: DbtProject, nodes: list[str], cap_s: int) -> dict:
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
    bg = BackgroundLoad(db, regime["background"])
    if regime["warm"]:
        prime(db)
    with bg:
        for rep in range(REPS):
            for variant, wt in (("main", WT_MAIN), ("pr", WT_PR)):
                ensure_worktree(CLONE, wt, rec["base_sha"] if variant == "main" else rec["head_sha"])
                proj = regime_project(wt, regime, db, profiles)
                proj.deps()
                r = build_once(proj, nodes, cap_s)
                r.update(variant=variant, rep=rep, regime=label)
                runs.append(r)
                if not r["ok"]:
                    return {"runs": runs, "ok": False, "background_queries": bg.queries}
    return {"runs": runs, "ok": True, "background_queries": bg.queries}


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
    args = ap.parse_args()
    cap_s = args.cap_minutes * 60

    recs = json.loads((RES / "reconstruction.json").read_text(encoding="utf-8"))
    usable = [r for r in recs if r.get("executable")]
    for i, r in enumerate(usable):
        r["split"] = "development" if i < 15 else ("holdout" if i < 40 else "reserve")

    write_profile(PROF_CI, DB_CI, CI["threads"], CI["memory"])
    write_profile(PROF_PROD, DB_PROD, PROD["threads"], PROD["memory"])
    (RES / "holdout_predictions").mkdir(parents=True, exist_ok=True)

    out_path = RES / "measurements.json"
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
        row = {"pr": rec["pr"], "split": rec["split"], "merged_at": rec["merged_at"],
               "base_sha": rec["base_sha"], "head_sha": rec["head_sha"],
               "subject": rec["subject"], "n_affected": rec["n_affected"],
               "affected": rec["affected"], "touched": rec["touched"]}

        # ---- Phase A: pre-merge CI prediction
        t0 = time.perf_counter()
        row["ci_db_copy_s"] = round(copy_db(DB_PROD, DB_CI), 1)
        a = measure_pair(rec, CI, DB_CI, PROF_CI, cap_s, "ci")
        row["phase_a"] = a
        row["phase_a_wall_s"] = round(time.perf_counter() - t0, 1)
        if not a["ok"]:
            row["outcome"] = "CI_BUILD_FAILED"
            row["detail"] = next((r["error"] for r in a["runs"] if not r["ok"]), "")[-1200:]
            done.append(row)
            out_path.write_text(json.dumps(done, indent=1), encoding="utf-8")
            print("   CI build failed", flush=True)
            continue
        pred = summarise(a["runs"])
        pred["grade"] = grade(pred)
        pred["analysis_wall_s"] = row["phase_a_wall_s"]
        pred["analysis_engine_s"] = sum(r["total_s"] for r in a["runs"])
        # production-run equivalents: engine seconds spent analysing / one production run of A
        base_run = pred["main"]["median_s"] or 0.0
        pred["k_production_runs"] = (pred["analysis_engine_s"] / base_run) if base_run else None
        row["prediction"] = pred
        row["prediction_sha256"] = freeze(
            RES / "holdout_predictions" / f"pr_{rec['pr']}.json",
            {"pr": rec["pr"], "split": rec["split"], "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "affected": rec["affected"], "prediction": pred})
        print(f"   prediction rel={pred['rel']} grade={pred['grade']} "
              f"k={pred['k_production_runs']}", flush=True)

        # ---- Phase B: shadow-production truth (prediction is already on disk and hashed)
        t1 = time.perf_counter()
        b = measure_pair(rec, PROD, DB_PROD, PROF_PROD, cap_s, "production")
        row["phase_b"] = b
        row["phase_b_wall_s"] = round(time.perf_counter() - t1, 1)
        if not b["ok"]:
            row["outcome"] = "PROD_BUILD_FAILED"
            row["detail"] = next((r["error"] for r in b["runs"] if not r["ok"]), "")[-1200:]
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
