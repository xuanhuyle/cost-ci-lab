"""Experiment 9 (H1): what does change detection see?

For every scenario compare three detectors against each other:
  files        the git diff (what a naive "changed .sql files" detector sees)
  dbt_state    dbt `state:modified` (raw-text + unrendered-config comparison), plus sub-selectors
  rendered     rendered-SQL diff of every model (comments/whitespace-normalised) + materialisation
The rendered diff is the reference for "what will actually run differently". Workload mapping
(state:modified+ and consumers) is taken from results/bench. Writes results/attribution.json.
"""
from __future__ import annotations

import json

from costci.paths import RESULTS
from costci.scenario import Workspace, load_scenarios, pr_project, rendered_diff


def main():
    ws = Workspace()
    out = {}
    for sc in load_scenarios():
        rec = json.loads((RESULTS / "bench" / f"{sc.id}.json").read_text(encoding="utf-8"))
        ch = rec["changes"]
        rendered = rendered_diff(ws, pr_project(ws, sc))
        dbt_mod = set(ch["modified"])
        out[sc.id] = {
            "changed_files": ch["changed_files"],
            "dbt_modified": sorted(dbt_mod),
            "dbt_modified_by": {k: v for k, v in ch["modified_by"].items() if v},
            "rendered_modified": rendered,
            "missed_by_dbt": sorted(set(rendered) - dbt_mod),
            "flagged_but_render_identical": sorted(dbt_mod - set(rendered)),
            "modified_plus": ch["modified_plus"],
            "consumers": ch["consumers"],
        }
        print(sc.id, "dbt:", sorted(dbt_mod), "rendered:", rendered, flush=True)
    (RESULTS / "attribution.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
