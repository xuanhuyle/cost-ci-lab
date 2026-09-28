# STATUS: Cost CI feasibility investigation

Last updated: 2026-09-28 ~13:05 (session 1)

## Hypothesis status (provisional; final verdicts go in docs/DECISION.md)
| ID | Hypothesis | Status | Evidence so far |
|----|-----------|--------|-----------------|
| H1 | Change attribution | Supported, with fixable blind spots | dbt state works for SQL text. Blind spots: var/env (E-017, s24), cosmetic false positives (s21). Consumers need access history (s10/s11 sign flips). |
| H2 | Counterfactual estimation | Supported **only** via production-scale execution | Full-clone A/B tracks truth. Samples, static and bytes err in both directions (s01, s06, s14, s17). |
| H3 | Production extrapolation | Partly | Anchor × ratio works in the lab. Frequency: crons exact, BI ±7%, seasonal/sparse unpredictable (E6). Pool economics: E2 pending. |
| H4 | Calibration | Designed (ARCHITECTURE §6); E7 pending | — |
| H5 | CI practicality | Narrow | A full-clone check costs ~4.5 production-run equivalents (median). Break-even needs ≳30–70 runs/month (E10). |
| H6 | Cross-platform abstraction | Survives only with explicit pool semantics | ARCHITECTURE §1, §7 |

## Done
- Research (4 streams) → `docs/research/*`, `docs/PLATFORM_FEASIBILITY.md`, EVIDENCE_LOG E-001..E-022.
- Lab: TPC-H SF2 + 4 CI envs; dbt project (17 models); 26 scenarios (s26 added; s15 is a data-dependent no-op).
- Harness and tests (18 pass). Docs drafted: EXPERIMENT_DESIGN, ARCHITECTURE (incl. §6 calibration, §7 portability), FAILURE_MODES, OWNER_REQUEST, README, RESULTS (partial). `live/snowflake/` kit (UNVALIDATED).
- E6 frequency and E10 CI economics done (on partial data).

## In progress
- E1 benchmark (background; `work/bench_run.log`; 20/25 done at 13:00).

## Next
1. `python -m experiments.followups`: s26 → E9 attribution (+ union re-run of dbt-missed scenarios) → baseline → analyze → E2 → E5 → E7 → E10 → prodfine + E8 → E3 → E4 → report. About 70 min, sequential.
2. Fill RESULTS §2–10 from `results/tables/*.md`; evidence entries E-023+; DECISION; final README; commit.

## Blockers
- No live platform access (`docs/OWNER_REQUEST.md`). The gcloud credentials on this machine belong to an unrelated project and are not used.
