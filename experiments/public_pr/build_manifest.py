"""F1: freeze the corpus frame.

Applies the pre-registered frame of docs/PUBLIC_CORPUS_PROTOCOL.md §2 to the mechanical census
and writes public_corpus/manifest.json. Nothing here looks at cost.

The realised development/holdout split is filled in later by reconstruct.py, which only ever
decides *usability* (does it build), never anything about the outcome.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CENSUS = ROOT / "public_corpus" / "census_tuva.json"
OUT = ROOT / "public_corpus" / "manifest.json"

REPO = "tuva-health/tuva-core"
WINDOW_START = "2026-02-04"      # the day Tuva's own DuckDB CI profile landed (PR #1193)
WINDOW_END = "2026-09-09"        # exclusive upper bound; clone HEAD is 2026-09-08
DEV_N = 10
HOLDOUT_N = 20


def cost_relevant(c: dict) -> bool:
    k = c["classes"]
    return bool(k["model_sql"] or k["macro_sql"] or k["project_cfg"])


def main() -> None:
    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    clone = ROOT / "work" / "corpus" / "tuva-core"
    clone_head = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
    rows = []
    for c in census["commits"]:
        if not (WINDOW_START <= c["merged_at"][:10] < WINDOW_END):
            continue
        if not cost_relevant(c):
            continue
        rows.append({
            "repository": REPO,
            "pr": c["pr"],
            "base_sha": c["base_sha"],
            "head_sha": c["sha"],
            "merged_at": c["merged_at"],
            "subject": c["subject"],
            "n_files": c["n_files"],
            "touched": c["classes"],
            "files": c["files"],
            "dataset_mapping": "tuva-public-resources S3, tuva_core_data_asset_version pinned "
                               "per commit by the repository itself",
            "executable": None,          # filled by reconstruct.py
            "exclusion": None,           # filled by reconstruct.py
            "split": None,               # filled by reconstruct.py
        })
    rows.sort(key=lambda r: r["merged_at"])
    for i, r in enumerate(rows):
        r["order"] = i
    manifest = {
        "frame": {
            "repository": REPO,
            "clone_head": clone_head,
            "unit": "first-parent squash-merge commit on main; MAIN = C^, PR = C",
            "window_start": WINDOW_START,
            "window_end_exclusive": WINDOW_END,
            "cost_relevant_rule": "diff touches a model .sql, a macro .sql, or project config",
            "n": len(rows),
            "split_rule": {"development": DEV_N, "holdout": HOLDOUT_N,
                           "assignment": "first DEV_N usable in merge order, then next HOLDOUT_N; "
                                         "remainder is reserve for bug-invalidated holdout cases"},
            "protocol": "docs/PUBLIC_CORPUS_PROTOCOL.md",
        },
        "prs": rows,
    }
    OUT.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"frame n={len(rows)}  {rows[0]['merged_at'][:10]}..{rows[-1]['merged_at'][:10]} -> {OUT}")


if __name__ == "__main__":
    main()
