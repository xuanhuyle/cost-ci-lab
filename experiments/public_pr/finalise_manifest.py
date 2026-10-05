"""F1: write the realised development/holdout split back into the corpus manifest.

Usability is a build/parse outcome only; nothing here looks at cost.
"""
import json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAN = ROOT / "public_corpus" / "manifest.json"
REC = ROOT / "results" / "public_pr" / "reconstruction.json"
FREEZE = ROOT / "results" / "public_pr" / "freeze.json"

man = json.loads(MAN.read_text(encoding="utf-8"))
recs = json.loads(REC.read_text(encoding="utf-8"))
by_pr = {r["pr"]: r for r in recs}
dev_n = man["frame"]["split_rule"]["development"]
hold_n = man["frame"]["split_rule"]["holdout"]

usable_order = [r["pr"] for r in recs if r.get("executable")]
split = {}
for i, pr in enumerate(usable_order):
    split[pr] = "development" if i < dev_n else ("holdout" if i < dev_n + hold_n else "reserve")

for row in man["prs"]:
    r = by_pr.get(row["pr"])
    if r is None:
        row["executable"] = None
        row["exclusion"] = None
        row["split"] = None
        continue
    row["executable"] = bool(r.get("executable"))
    row["exclusion"] = r.get("exclusion")
    row["split"] = split.get(row["pr"])
    row["n_affected"] = r.get("n_affected")
    row["affected"] = r.get("affected")
    row["state_modified"] = r.get("state_modified")

man["frame"]["realised"] = {
    "scanned": len(recs),
    "usable": len(usable_order),
    "excluded": len(recs) - len(usable_order),
    "development": [p for p, s in split.items() if s == "development"],
    "holdout": [p for p, s in split.items() if s == "holdout"],
    "reserve": [p for p, s in split.items() if s == "reserve"],
    "not_reached": [row["pr"] for row in man["prs"] if row["pr"] not in by_pr],
}
MAN.write_text(json.dumps(man, indent=1), encoding="utf-8")

sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                     capture_output=True, text=True).stdout.strip()
fr = json.loads(FREEZE.read_text(encoding="utf-8")) if FREEZE.exists() else {}
fr.setdefault("F1_corpus_manifest", {
    "git_sha_at_write": sha,
    "scanned": len(recs), "usable": len(usable_order),
    "development": man["frame"]["realised"]["development"],
    "holdout": man["frame"]["realised"]["holdout"],
})
FREEZE.write_text(json.dumps(fr, indent=1), encoding="utf-8")
print(json.dumps(man["frame"]["realised"], indent=1))
