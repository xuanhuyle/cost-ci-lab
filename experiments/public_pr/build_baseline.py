"""Build the shadow-production baseline database at the corpus window-start commit.

The production database must be in the state of `C^` of the first corpus PR, because the
experiment then walks main's history forward, deploying each PR in turn. Building it at HEAD
instead would make every early PR read relations produced by much later code.

One full `dbt build --full-refresh` of the whole project, in the production regime.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402

from costci.public_pr import DbtProject, ensure_worktree, write_profile  # noqa: E402

CLONE = ROOT / "work" / "corpus" / "tuva-core"
PUB = ROOT / "work" / "pub"
WT = PUB / "wt_prod"
PKG_CACHE = PUB / "pkgcache_prod"
DB = PUB / "db" / "prod.duckdb"
PROF = PUB / "profiles_prod"
MANIFEST = ROOT / "public_corpus" / "manifest.json"
OUT = ROOT / "results" / "public_pr" / "baseline_build.json"

THREADS, MEMORY = 4, "3GB"
DBT_VARS = {"synthetic_data_size": "large"}
SELECT = ["package:integration_tests", "package:the_tuva_project"]


def main() -> None:
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = man["prs"][0]["base_sha"]
    print(f"baseline commit {base} (C^ of PR #{man['prs'][0]['pr']}, "
          f"{man['prs'][0]['merged_at'][:10]})", flush=True)
    ensure_worktree(CLONE, WT, base)
    write_profile(PROF, DB, THREADS, MEMORY)
    DB.parent.mkdir(parents=True, exist_ok=True)
    DB.unlink(missing_ok=True)
    Path(str(DB) + ".wal").unlink(missing_ok=True)

    proj = DbtProject(WT, "integration_tests", PROF, PKG_CACHE, DB, THREADS, MEMORY)
    t0 = time.perf_counter()
    d = proj.deps()
    print(f"deps ok={d.ok} {d.seconds:.0f}s", flush=True)
    if not d.ok:
        print(d.error[-2000:])
        return
    r = proj.run(["build", "--full-refresh", "--select", *SELECT,
                  "--vars", json.dumps(DBT_VARS)], timeout=6 * 3600)
    wall = time.perf_counter() - t0
    # Fold the WAL in under a real memory limit and record how many relations the baseline
    # holds, so every later clone and deployment can be checked against it.
    con = duckdb.connect(str(DB), config={"memory_limit": "3GB"})
    con.execute("CHECKPOINT")
    relations = con.execute("SELECT count(*) FROM information_schema.tables").fetchone()[0]
    con.close()
    wal = Path(str(DB) + ".wal")
    if wal.exists() and wal.stat().st_size > 0:
        raise RuntimeError(f"WAL still present after CHECKPOINT ({wal.stat().st_size} bytes)")
    print(f"baseline relations: {relations}", flush=True)

    rr = proj.run_results()
    nodes = [{"unique_id": x.get("unique_id"), "status": x.get("status"),
              "execution_time": x.get("execution_time")} for x in rr.get("results", [])]
    ok = [n for n in nodes if n["status"] in ("success", "pass")]
    bad = [n for n in nodes if n["status"] in ("error", "fail")]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "baseline_commit": base, "ok": r.ok, "wall_s": round(wall, 1),
        "n_nodes": len(nodes), "n_ok": len(ok), "n_failed": len(bad),
        "relation_count": relations,
        "failed": [n["unique_id"] for n in bad][:80],
        "threads": THREADS, "memory_limit": MEMORY, "vars": DBT_VARS,
        "nodes": nodes, "error_tail": r.error[-4000:] if not r.ok else "",
    }, indent=1), encoding="utf-8")
    print(f"build ok={r.ok} wall={wall/60:.1f} min nodes={len(nodes)} "
          f"ok={len(ok)} failed={len(bad)}", flush=True)
    if bad:
        print("failed:", [n["unique_id"] for n in bad][:20], flush=True)


if __name__ == "__main__":
    main()
