"""Run every post-benchmark experiment sequentially (they must not overlap: they share the dbt
compile catalog and CPU contention would distort timings). Logs to work/followups.log.

Usage: python -m experiments.followups [--skip-measure]
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

from costci.paths import RESULTS, ROOT

PY = sys.executable


def step(args: list[str], log) -> None:
    t0 = time.perf_counter()
    log.write(f"\n=== {' '.join(args)}\n")
    log.flush()
    p = subprocess.run([PY, "-m", *args], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    log.write(f"=== exit {p.returncode} in {time.perf_counter() - t0:.0f}s\n")
    log.flush()
    print(f"{' '.join(args)}: exit {p.returncode} ({time.perf_counter() - t0:.0f}s)", flush=True)
    if p.returncode != 0:
        raise SystemExit(f"step failed: {args}")


def main():
    skip = "--skip-measure" in sys.argv
    with open(ROOT / "work" / "followups.log", "a", encoding="utf-8") as log:
        if not skip:
            step(["experiments.run_benchmark", "--only", "s26_include_future_shipments"], log)
            step(["experiments.attribution"], log)
            missed = [sid for sid, r in json.loads((RESULTS / "attribution.json").read_text(encoding="utf-8")).items()
                      if r["missed_by_dbt"]]
            if missed:
                step(["experiments.run_benchmark", "--detection", "union", "--only", *missed], log)
            step(["experiments.remeasure_consumers"], log)
            step(["experiments.measure_baseline"], log)
        step(["experiments.analyze"], log)
        step(["experiments.economics_run"], log)
        step(["experiments.uncertainty"], log)
        step(["experiments.calibration"], log)
        step(["experiments.ci_economics"], log)
        if not skip:
            step(["costci.data", "--only", "prodfine"], log)
            step(["experiments.layout"], log)
            step(["experiments.transfer"], log)
            step(["experiments.downstream"], log)
        step(["experiments.report"], log)


if __name__ == "__main__":
    main()
