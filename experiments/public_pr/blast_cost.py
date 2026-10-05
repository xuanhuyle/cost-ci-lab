"""How expensive is a counterfactual run of a natural PR's blast radius?

Joins the per-node execution times measured when the shadow-production baseline was built with
each PR's affected node set. This is the measured version of the prediction made in
docs/PUBLIC_CORPUS_SEARCH.md §3: counterfactual-execution cost scales with blast radius, and
natural PRs have a much larger blast radius than the previous stage's benchmark.

It uses only baseline (MAIN-side) costs, so it reveals nothing about any PR's outcome.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "public_pr"


def main() -> None:
    base = json.loads((RES / "baseline_build.json").read_text(encoding="utf-8"))
    recs = json.loads((RES / "reconstruction.json").read_text(encoding="utf-8"))
    node_s = {}
    for n in base["nodes"]:
        uid = n.get("unique_id") or ""
        if uid.startswith("model.") and n.get("execution_time") is not None:
            node_s[uid.split(".")[-1]] = float(n["execution_time"])
    full_job_s = sum(node_s.values())

    rows = []
    for r in recs:
        if not r.get("executable"):
            continue
        aff = r.get("affected") or []
        known = [n for n in aff if n in node_s]
        secs = sum(node_s[n] for n in known)
        rows.append({
            "pr": r["pr"], "merged_at": r["merged_at"], "n_affected": len(aff),
            "n_priced": len(known), "blast_seconds_per_run": round(secs, 2),
            "share_of_full_job": round(secs / full_job_s, 4) if full_job_s else None,
            # one counterfactual analysis = 2 variants x 2 reps of the blast radius
            "analysis_seconds": round(4 * secs, 2),
            "k_production_runs_of_blast": 4.0,
            "k_production_runs_of_full_job": round(4 * secs / full_job_s, 3) if full_job_s else None,
        })
    out = {
        "baseline_commit": base["baseline_commit"],
        "full_job_seconds": round(full_job_s, 1),
        "n_model_nodes_priced": len(node_s),
        "slowest_nodes": sorted(((round(v, 1), k) for k, v in node_s.items()), reverse=True)[:15],
        "n_prs": len(rows),
        "blast_seconds_median": round(st.median(r["blast_seconds_per_run"] for r in rows), 2) if rows else None,
        "blast_seconds_p90": (sorted(r["blast_seconds_per_run"] for r in rows)[int(.9 * len(rows)) - 1]
                              if rows else None),
        "blast_seconds_max": max((r["blast_seconds_per_run"] for r in rows), default=None),
        "share_of_full_job_median": round(st.median(r["share_of_full_job"] for r in rows), 4) if rows else None,
        "analysis_minutes_median": round(st.median(r["analysis_seconds"] for r in rows) / 60, 2) if rows else None,
        "n_over_45min_cap": sum(1 for r in rows if r["analysis_seconds"] > 45 * 60),
        "rows": rows,
    }
    (RES / "blast_cost.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1)[:2000])


if __name__ == "__main__":
    main()
