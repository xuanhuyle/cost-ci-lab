# STATUS — Cost CI feasibility investigation

Last updated: 2026-09-28 (session 1)

## Hypothesis status
| ID | Hypothesis | Status | Evidence so far |
|----|-----------|--------|-----------------|
| H1 | Change attribution (diff → workloads → history) | OPEN | — |
| H2 | Counterfactual estimation (Cost(PR) − Cost(MAIN)) | OPEN | — |
| H3 | Production extrapolation to recurring $ | OPEN | — |
| H4 | Post-merge calibration | OPEN | — |
| H5 | CI practicality (latency, analysis cost) | OPEN | — |
| H6 | Cross-platform abstraction | OPEN | — |

## Plan
1. [x] Inspect repo/environment. Repo contained only the brief. No Snowflake/Databricks credentials.
       gcloud has credentials for an unrelated project (not used; see OWNER_REQUEST).
2. [ ] Phase 1 platform research (parallel subagents → `docs/research/*.md`) → `docs/PLATFORM_FEASIBILITY.md`.
3. [ ] Local lab: DuckDB + real dbt (dbt-duckdb) on TPC-H, adapter-portable SQL.
       Measures resource ratios at production scale (ground truth) vs CI-feasible estimators.
4. [ ] Benchmark suite (~24 scenarios incl. adversarial) as overlays on a base dbt project.
5. [ ] Estimators A (static/plan), B (A/B full clone / samples), C (production-anchored),
       D (native-estimator analog), E (hybrid); pool/billing layer from documented pricing rules.
6. [ ] Metrics, uncertainty calibration, downstream propagation, CI economics.
7. [ ] Architecture + portability (Snowflake / Databricks / BigQuery) + failure modes.
8. [ ] Live-experiment kit + OWNER_REQUEST; DECISION.

## Competing hypotheses being tested (where uncertainty is material)
- HA: Relative resource ratios measured cheaply in CI (samples/static) transfer to production scale.
  HB: Ratios are scale-dependent for a material class of changes (joins, windows, spills), so only
      full-scale A/B is trustworthy → CI cost scales with production cost.
- HC: Per-workload attributed cost is a good proxy for marginal $ impact.
  HD: Marginal $ is a property of the capacity pool (warehouse/reservation), not the query; per-query
      attribution misleads on shared/prepaid capacity.

## Blockers
- No live platform access (see `docs/OWNER_REQUEST.md` once written).

## Next step
Launch research subagents; set up venv + dbt-duckdb; build base dbt project and measurement harness.
