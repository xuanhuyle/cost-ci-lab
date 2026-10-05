import json, statistics as st
from pathlib import Path
D = Path("public_corpus/raw")

def summarise(f, since=None):
    d = json.load(open(f))
    prs = d["prs"]
    if since: prs = [p for p in prs if p["merged_at"] >= since]
    rel = [p for p in prs if p["classes"]["model_sql"] or p["classes"]["macro_sql"] or p["classes"]["project_cfg"]]
    if not rel: return None
    nf = [p["n_files"] for p in rel]; ms = [p["classes"]["model_sql"] for p in rel]
    add = [p["additions"] for p in rel]
    def pct(f_): return 100.0 * sum(1 for p in rel if f_(p)) / len(rel)
    return {
        "repo": d["repo"], "since": since or "all", "merged_scanned": len(prs), "cost_relevant": len(rel),
        "files_median": st.median(nf), "files_p90": sorted(nf)[int(.9*len(nf))-1],
        "model_sql_median": st.median(ms), "additions_median": st.median(add),
        "pct_single_model": pct(lambda p: p["classes"]["model_sql"] == 1),
        "pct_multi_model": pct(lambda p: p["classes"]["model_sql"] > 1),
        "pct_ge10_models": pct(lambda p: p["classes"]["model_sql"] >= 10),
        "pct_macro": pct(lambda p: p["classes"]["macro_sql"] > 0),
        "pct_project_cfg": pct(lambda p: p["classes"]["project_cfg"] > 0),
        "pct_yml_only": pct(lambda p: p["classes"]["model_sql"] == 0 and p["classes"]["macro_sql"] == 0),
        "pct_seed_csv": pct(lambda p: p["classes"]["seed_csv"] > 0),
    }

rows = [
    summarise(D/"prs_tuva-health_tuva-core.json"),
    summarise(D/"prs_tuva-health_tuva-core.json", "2026-02-04"),
    summarise(D/"prs_cal-itp_data-infra.json"),
    summarise(D/"prs_OHDSI_dbt-synthea.json"),
    summarise(D/"prs_matsonj_nba-monte-carlo.json"),
    summarise(D/"prs_dcaribou_transfermarkt-datasets.json"),
]
rows = [r for r in rows if r]
json.dump(rows, open(D/"structure.json","w"), indent=1)
hdr = ["repo","since","cost_relevant","files_median","model_sql_median","pct_single_model","pct_multi_model","pct_ge10_models","pct_macro","pct_project_cfg","pct_yml_only"]
print(" | ".join(hdr))
for r in rows:
    print(" | ".join(f"{r[h]:.0f}" if isinstance(r[h], float) else str(r[h]) for h in hdr))
