# Cost CI: technical feasibility investigation

**Question.** Can a pre-merge cost-diff engine produce estimates reliable enough to influence merge
decisions? The governing brief is [`COST_CI_TECHNICAL_FEASIBILITY_CLAUDE_CODE.md`](COST_CI_TECHNICAL_FEASIBILITY_CLAUDE_CODE.md).

**Start with [`docs/DECISION.md`](docs/DECISION.md)** for the verdict and the answers to the brief's
ten final questions.

**Verdict: B, "Useful but narrow".**
- **What works:** measuring the change, not predicting it. Run the changed dbt workloads at
  production scale (a zero-copy clone, or PR-only against production history), then replay the
  capacity pool's billing.
  - Lab result on 26 adversarial PRs: 100% direction on material changes, 100% large-regression
    recall, ~10% median magnitude error, and calibrated noise-based intervals.
- **What does not work:** every cheap alternative. Static plans, dry-run-style bytes, four data-sampling
  schemes, scale extrapolation and calibration all made wrong-sign or missed-material errors.
- **Where it pays off:** reliable checks cost ~2.5–4.6 production runs per analysis, so they break
  even only on workloads run more than ~40–70 times a month.
- **Where the dollars mean something:** dollar impact is unambiguous only on dedicated or
  per-query-billed compute. On shared or prepaid capacity it depends on policy.
- **The limit of the evidence:** all execution evidence is from a local engine. No live platform
  access was available (see `docs/OWNER_REQUEST.md`).

## What is here

| Path | What |
|---|---|
| `docs/DECISION.md` | Final technical outcome (A/B/C/D) and the ten answers |
| `docs/RESULTS.md` | All results; local/simulated results are kept apart from documented facts (no live results exist yet) |
| `docs/PLATFORM_FEASIBILITY.md` | Phase 1: what Snowflake / Databricks / BigQuery / dbt expose, with classifications and sources |
| `docs/ARCHITECTURE.md` | Phase 2: is "cost impact of a change" a platform-independent object? Revised interface |
| `docs/EXPERIMENT_DESIGN.md` | Lab, 25-PR benchmark, protocol, estimators, metrics, threats to validity, reproduction |
| `docs/FAILURE_MODES.md` | Phase 8: each failure mode classified (solvable / statistical / uncertainty / config / unpredictable) |
| `docs/EVIDENCE_LOG.md` | Every material claim with its evidence level and source |
| `docs/OWNER_REQUEST.md` | The only items that need the owner (live platform access) |
| `docs/research/` | Raw primary-source research notes per platform (~300 URLs) |
| `costci/` | Harness: data environments, dbt wrapper, scenario/change detection, measurement, estimators, pools/billing, economics, metrics, provider capability matrix |
| `benchmark/` | Base dbt project (TPC-H, adapter-portable), 25 scenario PRs, synthetic production context |
| `experiments/` | E1–E8 drivers. They write `results/` |
| `results/` | Measured and computed outputs (JSON + markdown tables) |
| `live/snowflake/` | Prepared but unexecuted live experiment: setup/teardown SQL, telemetry SQL, adapter, runbook |
| `tests/` | Unit tests for billing rules, metrics, provider matrix |

## Evidence discipline

- **Research:** documented platform facts carry the `DOCUMENTED` label.
- **Experiments:** everything executable ran on a local DuckDB engine with real dbt and is labelled
  `MEASURED (local engine)`. None of it is proof of Snowflake, Databricks or BigQuery behaviour.
- **Dollars:** the dollar layer applies documented billing rules to a synthetic production month, so
  it is `SIMULATED`.
- **No LLM** is used anywhere in the estimation path.

## Reproduce

See [`docs/EXPERIMENT_DESIGN.md` §9](docs/EXPERIMENT_DESIGN.md#9-reproduce). A 4-core laptop needs
about 2.5 h end to end and about 2 GB of disk. `pytest -q` runs the unit tests.
