"""Phase 3: reconstruct each natural PR and record what the change-detection layer sees.

For every PR in public_corpus/manifest.json, in merge order:
  1. check out C^ (MAIN) and C (PR) into two reusable worktrees;
  2. install the dependency set pinned at that commit (cached by dependency-file hash);
  3. dbt parse both;
  4. dbt state:modified (and sub-selectors) of PR against MAIN;
  5. a changed-var detector (the class dbt state:modified provably misses, E-023);
  6. descendants (state:modified+ plus descendants of rendered-only changes);
  7. record compile failures and the allowed exclusion code, if any.

Nothing here executes a model, and nothing here looks at cost.
Usability decisions are build/parse outcomes only (protocol §5).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from costci.public_pr import DbtProject, ensure_worktree, git, write_profile  # noqa: E402

CLONE = ROOT / "work" / "corpus" / "tuva-core"
PUB = ROOT / "work" / "pub"
WT_MAIN = PUB / "wt_main"
WT_PR = PUB / "wt_pr"
PKG_CACHE = PUB / "pkgcache"
STATE = PUB / "state"
PROFILES_COMPILE = PUB / "profiles_compile"
COMPILE_DB = PUB / "db" / "compile.duckdb"
MANIFEST = ROOT / "public_corpus" / "manifest.json"
OUT = ROOT / "results" / "public_pr" / "reconstruction.json"
EXCL = ROOT / "results" / "public_pr" / "exclusion_log.json"

PROJECT_SUBDIR = "integration_tests"
DBT_VARS = {"synthetic_data_size": "large"}
SUBSELECTORS = ("body", "configs", "macros", "relation", "persisted_descriptions", "contract")


def changed_vars(base_sha: str, head_sha: str) -> list[str]:
    """Top-level `vars:` keys whose value changed in dbt_project.yml between the two commits.

    dbt `state:modified` compares *unrendered* config and cannot see a changed var default
    (E-023, dbt-core#4304). A full rendered-SQL diff would catch it but needs a populated
    warehouse to compile this project, so the targeted substitute is: find the changed vars, then
    find every node whose code reads them.
    """
    import yaml
    out = []
    try:
        a = yaml.safe_load(git(CLONE, "show", f"{base_sha}:dbt_project.yml")) or {}
        b = yaml.safe_load(git(CLONE, "show", f"{head_sha}:dbt_project.yml")) or {}
    except Exception:
        return out
    va, vb = (a.get("vars") or {}), (b.get("vars") or {})
    for k in sorted(set(va) | set(vb)):
        if va.get(k) != vb.get(k):
            out.append(k)
    return out


VAR_RE_CACHE: dict[str, "re.Pattern"] = {}


def nodes_reading_vars(project: DbtProject, names: list[str]) -> list[str]:
    """Models whose raw code, or a macro they depend on, reads one of these vars."""
    if not names:
        return []
    import re
    man = project.manifest()
    pats = [re.compile(r"var\s*\(\s*['\"]" + re.escape(n) + r"['\"]") for n in names]
    hit_macros = {uid for uid, m in man.get("macros", {}).items()
                  if any(p.search(m.get("macro_sql") or "") for p in pats)}
    out = []
    for uid, n in man.get("nodes", {}).items():
        if n.get("resource_type") != "model":
            continue
        code = (n.get("raw_code") or "")
        if any(p.search(code) for p in pats) or (set(n.get("depends_on", {}).get("macros") or [])
                                                 & hit_macros):
            out.append(uid)
    return out


def node_names(ids: list[str]) -> list[str]:
    return sorted({i.split(".")[-1] for i in ids})


def reconstruct_one(row: dict, do_rendered: bool) -> dict:
    rec = {"pr": row["pr"], "order": row["order"], "merged_at": row["merged_at"],
           "base_sha": row["base_sha"], "head_sha": row["head_sha"], "subject": row["subject"],
           "touched": row["touched"], "n_files": row["n_files"]}
    t0 = time.perf_counter()
    ensure_worktree(CLONE, WT_MAIN, row["base_sha"])
    ensure_worktree(CLONE, WT_PR, row["head_sha"])
    mk = lambda wt: DbtProject(wt, PROJECT_SUBDIR, PROFILES_COMPILE, PKG_CACHE,  # noqa: E731
                               COMPILE_DB, threads=1, memory_limit="2GB")
    main, pr = mk(WT_MAIN), mk(WT_PR)

    for name, proj in (("main", main), ("pr", pr)):
        r = proj.deps()
        if not r.ok:
            rec.update(executable=False, exclusion="X1_DEPS",
                       detail=f"deps failed on {name}: {r.error[-400:]}")
            return rec

    pr_parse = pr.parse(DBT_VARS)
    main_parse = main.parse(DBT_VARS)
    rec["parse_seconds"] = round(pr_parse.seconds + main_parse.seconds, 1)
    if not (main_parse.ok and pr_parse.ok):
        both = (not main_parse.ok) and (not pr_parse.ok)
        rec.update(executable=False, exclusion="X2_PARSE" if both else "PARSE_PR_ONLY",
                   detail=(main_parse.error or pr_parse.error)[-600:])
        if not both:
            # only one side fails: that is a property of the change, not of the environment.
            # Not an allowed exclusion; recorded and carried forward as a build failure.
            rec["exclusion"] = None
            rec["executable"] = False
            rec["detail"] = ("parse fails on %s only" %
                             ("main" if not main_parse.ok else "pr")) + " :: " + rec["detail"]
        return rec

    main.save_state(STATE)
    modified, r = pr.ls("state:modified", STATE, dbt_vars=DBT_VARS)
    rec["state_modified"] = node_names(modified)
    rec["modified_by"] = {}
    for s in SUBSELECTORS:
        ids, _ = pr.ls(f"state:modified.{s}", STATE, dbt_vars=DBT_VARS)
        rec["modified_by"][s] = node_names(ids)
    plus, _ = pr.ls("state:modified+", STATE, dbt_vars=DBT_VARS)
    rec["state_modified_plus"] = node_names(plus)

    if do_rendered:
        t1 = time.perf_counter()
        cv = changed_vars(row["base_sha"], row["head_sha"])
        rec["changed_vars"] = cv
        extra_ids = nodes_reading_vars(pr, cv)
        extra = [n for n in node_names(extra_ids) if n not in rec["state_modified"]]
        rec["var_only_models"] = extra
        if extra:
            ids, _ = pr.ls(" ".join(f"{n}+" for n in extra), dbt_vars=DBT_VARS)
            rec["state_modified_plus"] = sorted(set(rec["state_modified_plus"])
                                                | set(node_names(ids)))
        rec["var_detector_seconds"] = round(time.perf_counter() - t1, 1)

    rec["affected"] = rec["state_modified_plus"]
    rec["n_affected"] = len(rec["affected"])
    rec["executable"] = True
    rec["exclusion"] = None
    if not rec["affected"]:
        rec["executable"] = False
        rec["exclusion"] = "X4_NO_GRAPH"
        rec["detail"] = "diff produces no node in the compiled graph on this engine"
    rec["reconstruct_seconds"] = round(time.perf_counter() - t0, 1)
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="stop after N PRs (0 = until split full)")
    ap.add_argument("--start", type=int, default=0, help="manifest order index to start at")
    ap.add_argument("--no-rendered", action="store_true",
                help="skip the changed-var detector (dbt state:modified only)")
    args = ap.parse_args()

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    need = man["frame"]["split_rule"]["development"] + man["frame"]["split_rule"]["holdout"]
    write_profile(PROFILES_COMPILE, COMPILE_DB, threads=1, memory_limit="2GB")
    COMPILE_DB.parent.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    seen = {d["pr"] for d in done}
    usable = sum(1 for d in done if d.get("executable"))

    for row in man["prs"]:
        if row["order"] < args.start or row["pr"] in seen:
            continue
        if args.limit and len(done) - len([1 for d in done if d["pr"] in seen]) >= args.limit:
            break
        if not args.limit and usable >= need:
            break
        print(f"[{row['order']:>3}] PR #{row['pr']} {row['merged_at'][:10]} "
              f"{row['subject'][:60]}", flush=True)
        try:
            rec = reconstruct_one(row, do_rendered=not args.no_rendered)
        except Exception as e:                                  # noqa: BLE001
            import traceback; traceback.print_exc()
            rec = {"pr": row["pr"], "order": row["order"], "merged_at": row["merged_at"],
                   "executable": False, "exclusion": None, "detail": f"harness error: {e!r}"}
        done.append(rec)
        if rec.get("executable"):
            usable += 1
        print(f"      -> executable={rec.get('executable')} "
              f"excl={rec.get('exclusion')} affected={rec.get('n_affected')} "
              f"({rec.get('reconstruct_seconds')}s)  usable={usable}/{need}", flush=True)
        OUT.write_text(json.dumps(done, indent=1), encoding="utf-8")
        if args.limit and len(done) >= args.limit:
            break

    # exclusion log
    excl = [{"pr": d["pr"], "merged_at": d.get("merged_at"), "code": d.get("exclusion"),
             "detail": (d.get("detail") or "")[:400], "phase": "reconstruction",
             "decided_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "outcome_known_at_exclusion": False}
            for d in done if not d.get("executable")]
    EXCL.write_text(json.dumps(excl, indent=1), encoding="utf-8")
    print(f"\nreconstructed={len(done)} usable={usable} excluded={len(excl)}")


if __name__ == "__main__":
    main()
