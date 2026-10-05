"""Scan merged PRs of a repo: which touch cost-relevant dbt/SQL transformation code.

Writes work/corpus_search/prs_<owner>_<repo>.json  (raw, reusable for structural analysis).
No selection on 'looks expensive' happens here; this is a census.
"""
import json, subprocess, sys, time, re
from pathlib import Path

OUT = Path(__file__).parent

def api(path, paginate=False):
    args = ["gh", "api", "--cache", "6h"]
    if paginate: args.append("--paginate")
    args.append(path)
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0: return None
    txt = r.stdout.strip()
    if paginate:  # gh --paginate concatenates JSON arrays: ][ -> ,
        txt = txt.replace("][", ",")
    try: return json.loads(txt)
    except Exception: return None

SQLISH = (".sql",)
CFGISH = ("dbt_project.yml", "packages.yml", "profiles.yml", "package-lock.yml")

def classify(paths, model_dirs):
    c = {"sql": 0, "model_sql": 0, "macro_sql": 0, "yml": 0, "project_cfg": 0,
         "seed_csv": 0, "py": 0, "other": 0, "test_sql": 0}
    for p in paths:
        low = p.lower()
        if low.endswith(".sql"):
            c["sql"] += 1
            if "/macros/" in low or low.startswith("macros/"): c["macro_sql"] += 1
            elif "/tests/" in low or low.startswith("tests/"): c["test_sql"] += 1
            elif any(low.startswith(d) or f"/{d}" in low for d in model_dirs): c["model_sql"] += 1
            else: c["other"] += 1
        elif low.endswith((".yml", ".yaml")):
            if any(low.endswith(x) for x in CFGISH): c["project_cfg"] += 1
            else: c["yml"] += 1
        elif low.endswith(".csv"): c["seed_csv"] += 1
        elif low.endswith(".py"): c["py"] += 1
        else: c["other"] += 1
    return c

def main(repo, limit, model_dirs):
    owner, name = repo.split("/")
    prs = []
    page = 1
    while len(prs) < limit:
        batch = api(f"repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=100&page={page}")
        if not batch: break
        merged = [p for p in batch if p.get("merged_at")]
        prs.extend(merged)
        page += 1
        if page > 40: break
    prs = prs[:limit]
    rows = []
    for i, p in enumerate(prs):
        files = api(f"repos/{repo}/pulls/{p['number']}/files?per_page=100", paginate=True) or []
        paths = [f["filename"] for f in files]
        add = sum(f.get("additions", 0) for f in files)
        dele = sum(f.get("deletions", 0) for f in files)
        c = classify(paths, model_dirs)
        rows.append({
            "number": p["number"], "title": p["title"], "merged_at": p["merged_at"],
            "base_sha": p["base"]["sha"], "head_sha": p["head"]["sha"],
            "merge_commit_sha": p.get("merge_commit_sha"),
            "n_files": len(paths), "additions": add, "deletions": dele,
            "classes": c, "paths": paths[:400],
        })
        if (i+1) % 25 == 0: print(f"  ...{i+1}/{len(prs)}", file=sys.stderr)
    out = OUT / f"prs_{owner}_{name}.json"
    out.write_text(json.dumps({"repo": repo, "model_dirs": model_dirs, "prs": rows}, indent=1))
    rel = [r for r in rows if r["classes"]["model_sql"] or r["classes"]["macro_sql"] or r["classes"]["project_cfg"]]
    dates = sorted(r["merged_at"] for r in rows)
    print(f"{repo}: merged scanned={len(rows)} cost-relevant={len(rel)} "
          f"range={dates[0][:10]}..{dates[-1][:10]} -> {out.name}")

if __name__ == "__main__":
    repo = sys.argv[1]; limit = int(sys.argv[2]); dirs = sys.argv[3].split(",")
    main(repo, limit, dirs)
