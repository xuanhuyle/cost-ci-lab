# STATUS: Cost CI feasibility investigation

Last updated: 2026-09-28 12:40 (session 1)

## Hypothesis status (provisional, updated as results land)
| ID | Hypothesis | Status | Evidence so far |
|----|-----------|--------|-----------------|
| H1 | Change attribution | Largely supported, with known blind spots | dbt state works for SQL-text changes. Blind spots: var/env (E-017), cosmetic false positives, consumers need access history. |
| H2 | Counterfactual estimation | Supported only via production-scale execution (partial E1) | Full-clone A/B tracks truth; samples, static and bytes are off by large factors both ways. |
| H3 | Production extrapolation | Partly | Anchor × ratio works in the lab. Frequency is fine for crons and bad for sparse/seasonal (E6, simulated). Pool economics: pending E2. |
| H4 | Calibration | Pending E7 | — |
| H5 | CI practicality | Doubtful for heavy workloads | Reliable strategy costs about 1–2 production runs per affected workload per CI run. |
| H6 | Cross-platform abstraction | Survives only with explicit pool semantics | PLATFORM_FEASIBILITY §1, ARCHITECTURE §1 |

## Done
- Repo and venv; research on all 4 streams → `docs/research/*`, `docs/PLATFORM_FEASIBILITY.md`, EVIDENCE_LOG E-001..E-022.
- Lab: TPC-H SF2 plus 4 CI sample envs; dbt project (17 models); 25 scenarios; harness; tests (18 pass).
- Docs drafted: EXPERIMENT_DESIGN, ARCHITECTURE, OWNER_REQUEST, README; live/snowflake kit (UNVALIDATED).
- E6 frequency (simulated) done → `results/frequency.json`.

## In progress
- E1 benchmark running in the background (`work/bench_run.log`; ~2.5 min per scenario; results in `results/bench/`).

## Next (in order; do not run measurement experiments concurrently)
1. After E1: `experiments.measure_baseline` → `analyze` → `economics_run` → `uncertainty` → `calibration`.
2. `costci.data --only prodfine` → `experiments.layout` (physical-layout sensitivity: SF2 row groups span ~26 days, so incremental-window truth is scale-limited).
3. `experiments.transfer` (1 thread vs 4, concurrent load, cold run), then `experiments.downstream`.
4. Write RESULTS, FAILURE_MODES, DECISION; update ARCHITECTURE §5 and README; final commit.

## Blockers
- No live platform access (`docs/OWNER_REQUEST.md`). The gcloud credentials on this machine belong to an unrelated project and are not used.
