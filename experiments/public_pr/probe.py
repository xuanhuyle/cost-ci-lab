import json, subprocess, sys, datetime

REPOS = sys.argv[1:]

def gh(args):
    r = subprocess.run(["gh"]+args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip(), r.returncode

def api(path):
    out, rc = gh(["api", path])
    if rc != 0: return None
    try: return json.loads(out)
    except Exception: return None

for repo in REPOS:
    info = api(f"repos/{repo}")
    if not info:
        print(f"{repo:<42} MISSING"); continue
    # merged PR count via search
    s = api(f"search/issues?q=repo:{repo}+is:pr+is:merged&per_page=1")
    merged = s.get("total_count") if s else None
    # does it have dbt_project.yml anywhere near root?
    tree = api(f"repos/{repo}/git/trees/{info['default_branch']}?recursive=1")
    paths = [t["path"] for t in (tree or {}).get("tree", [])] if tree else []
    dbtp = [p for p in paths if p.endswith("dbt_project.yml")]
    models = sum(1 for p in paths if ("/models/" in p or p.startswith("models/")) and p.endswith(".sql"))
    seeds = sum(1 for p in paths if ("/seeds/" in p or p.startswith("seeds/")) and p.endswith(".csv"))
    profiles = [p for p in paths if p.endswith("profiles.yml")]
    print(f"{repo:<42} stars={info['stargazersCount'] if 'stargazersCount' in info else info['stargazers_count']:<6} "
          f"merged_prs={merged!s:<6} dbt_project={len(dbtp):<2} models.sql={models:<5} seeds.csv={seeds:<4} "
          f"pushed={info['pushed_at'][:10]} created={info['created_at'][:10]}")
    if dbtp: print(f"    dbt_project.yml: {dbtp[:4]}")
    if profiles: print(f"    profiles.yml:    {profiles[:3]}")
