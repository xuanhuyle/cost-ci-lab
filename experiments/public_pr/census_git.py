"""Authoritative chronological census of merged PRs from first-parent main history.

Unit of analysis: one squash-merge commit C on main.
  MAIN version = C^ (exact tree before the PR)
  PR   version = C  (exact tree with the PR merged)
Both are real, buildable states of the project. No reconstruction approximation.
"""
import json, re, subprocess, sys
from pathlib import Path

REPO = Path(sys.argv[1]); SINCE = sys.argv[2]; MODEL_DIRS = sys.argv[3].split(","); OUT = Path(sys.argv[4])
PRNUM = re.compile(r"\(#(\d+)\)\s*$")

def git(*a):
    return subprocess.run(["git","-C",str(REPO),*a], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout

log = git("log","--first-parent","main",f"--since={SINCE}","--format=%H|%cI|%s")
rows = []
for line in log.splitlines():
    if not line.strip(): continue
    sha, date, subj = line.split("|", 2)
    m = PRNUM.search(subj)
    files = [f for f in git("diff","--name-only",f"{sha}^",sha).splitlines() if f.strip()]
    if not files: continue
    c = {"model_sql":0,"macro_sql":0,"test_sql":0,"other_sql":0,"project_cfg":0,"yml":0,"seed_csv":0,"py":0,"other":0}
    for p in files:
        low = p.lower()
        if low.endswith(".sql"):
            if "macros/" in low: c["macro_sql"] += 1
            elif low.startswith("tests/") or "/tests/" in low: c["test_sql"] += 1
            elif any(d in low for d in MODEL_DIRS): c["model_sql"] += 1
            else: c["other_sql"] += 1
        elif low.endswith(("dbt_project.yml","packages.yml","package-lock.yml")): c["project_cfg"] += 1
        elif low.endswith((".yml",".yaml")): c["yml"] += 1
        elif low.endswith(".csv"): c["seed_csv"] += 1
        elif low.endswith(".py"): c["py"] += 1
        else: c["other"] += 1
    rows.append({"pr": int(m.group(1)) if m else None, "sha": sha, "base_sha": git("rev-parse",f"{sha}^").strip(),
                 "merged_at": date, "subject": subj, "n_files": len(files), "classes": c, "files": files[:500]})
rows.sort(key=lambda r: r["merged_at"])
OUT.write_text(json.dumps({"repo": str(REPO), "since": SINCE, "model_dirs": MODEL_DIRS, "commits": rows}, indent=1))
rel = [r for r in rows if r["classes"]["model_sql"] or r["classes"]["macro_sql"] or r["classes"]["project_cfg"]]
print(f"first-parent commits={len(rows)} cost-relevant={len(rel)} "
      f"range={rows[0]['merged_at'][:10]}..{rows[-1]['merged_at'][:10]} -> {OUT}")
