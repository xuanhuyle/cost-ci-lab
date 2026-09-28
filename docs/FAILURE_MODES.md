# Failure modes: attacking the idea (Phase 8)

Each failure mode gets a mechanism, the evidence (`DOCUMENTED` platform facts, `MEASURED (local)`
lab results, `SIMULATED` economics) and one classification:

| Class | Meaning |
|---|---|
| **DET** — SOLVABLE_DETERMINISTICALLY | A correct procedure exists with no residual uncertainty |
| **STAT** — SOLVABLE_STATISTICALLY | Repetition or history drives the error down to a known level |
| **UNC** — MANAGEABLE_WITH_UNCERTAINTY | Cannot be removed, but can be bounded and shown as an interval or grade |
| **CFG** — REQUIRES_CUSTOMER_CONFIGURATION | Needs information that is not in code or telemetry |
| **NRP** — NOT_RELIABLY_PREDICTABLE_PRE_DEPLOYMENT | No pre-merge procedure gives a decision-grade answer |

Lab experiment IDs (E1–E8) refer to `RESULTS.md`; evidence IDs (E-0xx) refer to `EVIDENCE_LOG.md`.

## Summary table

| # | Failure mode | Class | One-line reason |
|---|---|---|---|
| 1 | Query/result caches (CI measurement) | DET | Disable the result cache, discard warm-ups, interleave runs; Databricks' disk cache cannot be disabled, so warmth must be measured |
| 2 | Result caches in production consumers | UNC | A PR can change cacheability of downstream BI queries; hit rates come from history, but the PR's effect on them is not measurable in CI |
| 3 | Shared warehouses / clusters | UNC (+CFG) | Marginal $ is a pool property (replay needs the pool timeline); attribution is an allocation; the "marginal vs attributed" policy is a customer choice |
| 4 | Concurrency | UNC | Slowdown under contention depends on co-running load (E3); the ratio mostly transfers, absolute costs do not |
| 5 | Autoscaling | DET for BigQuery; UNC for Snowflake multi-cluster; NRP for Databricks serverless IWM | Only BigQuery's autoscaler rules are numerically documented (50 slots, ≥60 s) |
| 6 | Idle / already-paid-for capacity | CFG + DET | Once the pool state and policy are known, replay is deterministic; whether consuming headroom "costs" anything is a policy question |
| 7 | Capacity commitments / reservations | CFG | Commitment levels and baseline slots come from config or reservations telemetry; marginal $ is 0 until saturation, then a step |
| 8 | Negotiated pricing | CFG | Snowflake: `RATE_SHEET_DAILY` (org billing role only); Databricks: not exposed at all; BigQuery: billing export (~1 day) |
| 9 | Underlying cloud VM / network / storage (Databricks classic) | CFG | Billed by the cloud provider outside Databricks; needs a cloud-billing join via tags |
| 10 | Serverless vs provisioned | DET | Pool type is in telemetry; the billing function differs; serverless per-query billing makes attribution ≈ marginal |
| 11 | Data growth | STAT for linear workloads; UNC for scale-dependent changes | Ratios drift with scale for joins/sorts/parallelism (E1 sample→prod, E8) |
| 12 | Schedule / frequency changes | DET if the schedule is in the diff; NRP otherwise | Frequency changes made in orchestrator UIs are invisible to the PR |
| 13 | Frequency estimation from history | STAT (cron) / UNC (BI, data-driven) / NRP (seasonal peaks, sparse ad hoc) | E6 (simulated) |
| 14 | Downstream recomputation | DET (identification); STAT/UNC (magnitude) | Lineage is exact; the cost of unchanged descendants depends on data and layout (E4) |
| 15 | Incremental models | DET (reproduce the incremental branch via clone); UNC (recurring volume per run) | CI must build the incremental branch (E-003); steady-state volume depends on data arrival and pruning granularity (E8) |
| 16 | Retries | STAT | Retry rates live in telemetry (`query_retry_time`, BigQuery counts up to 3 attempts in slot-ms) |
| 17 | Orchestration that skips work (dbt State, state-aware) | UNC | Rebuild frequency becomes data-dependent (`DOCUMENTED`); the multiplier is itself a forecast |
| 18 | Dynamic SQL / introspective macros | DET at compile time (rendered-SQL diff against prod metadata); NRP for future data-driven changes | `state:modified` compares raw text only (E-004, E-017) |
| 19 | Python / Spark workloads | UNC (job compute, serverless jobs); NRP (shared all-purpose clusters) | No SQL plan; execution is the only estimator; attribution exists only for job-run-scoped compute (E-013) |
| 20 | Materialisation changes | DET (identification) + needs consumer discovery | Cost moves between the build and consumers; DAG-only estimators get the sign wrong (s10/s11) |
| 21 | Workload seasonality | CFG / NRP | Unseen peaks cannot be learned from trailing history (E6: 67% miss) |
| 22 | Sparse workloads | UNC | Tiny samples of run history: forecasts are ±100% (E6) |
| 23 | Cross-workload interactions | NRP (beyond the pool replay) | E.g. upstream physical layout changing downstream cost (s08 key10), cache sharing, clustering maintenance |
| 24 | Change-detection blind spots (vars, env vars, target Jinja) | DET | Diff the rendered SQL of both sides, as dbt's "dbt State" does (E-017; s24) |
| 25 | Serverless side-costs (auto-clustering, MV / dynamic-table refresh, `OPTIMIZE`) | UNC / NRP | Not in query attribution; the vendors' own estimators are ±50–100% (E-010) |
| 26 | Measurement noise | STAT | 5–29% CV per single run in the lab (E-009); needs repetition, interleaving and paired ratios |
| 27 | Scale transfer from samples | NRP for sample-based magnitude | See E1 results: sample ratios err in both directions by large factors |
| 28 | CI warehouse size ≠ production size | UNC | Parallel efficiency differs; latency ratios shift (E3) |
| 29 | Plan / optimizer drift | UNC | Snowflake Optima and BigQuery history-based optimisation: the first CI run is not steady state (`DOCUMENTED`) |
| 30 | Telemetry latency | DET (design) | Read real-time execution metrics in CI; reconcile $ asynchronously (3–24 h) |

## Lab evidence behind the classifications (`MEASURED (local engine)` unless stated)

- **Consumers flip the verdict (row 20).** A dbt-DAG-only estimate, even on a full production
  clone, reads s10 (table→view) as −4% when the truth is +152%, and s11 (view→table) as 0% when the
  truth is −89%. Adding the BI consumers of the changed relations gives +143% and −92%.
- **Static plans get signs wrong (rows 27, 11).**
  - s14 (join pre-aggregation, truth −29%): the C_out estimate says +127%.
  - s17 (window functions, truth +56% per run): static and bytes both say 0%. The change is
    compute-bound and moves no bytes.
- **Bytes ≠ compute (row 10).** s02 (pruning defeated): logical bytes +230%, engine time ≈ +4%.
  A byte-priced platform would bill +230%; a time-billed one ≈ +4%.
- **Samples get signs wrong (row 27).**
  - s14: the key-consistent-sample two-point estimate says +21% (truth −29%).
  - s01 (widened window): the 10% sample says +297% (truth +116%).
  - s06 (super-linear join, truth +1,413%): the 1% key-consistent sample says +4%.
- **Resource definition matters (rows 4, 28).** For the same model and change, the latency ratio
  and the CPU-work ratio differ by up to ~3× (s01 `int_order_lines`: 2.45× vs 6.9×). Parallel
  efficiency differs between MAIN and PR and changes with data size.
- **Data-dependent no-op (row 18).** In s15, a filter removal that reads as "+33% rows" removes
  nothing on this data; the truth is ≈0. Only execution reveals this.
- **Cross-workload physical effects (row 23).** An unchanged downstream model's cost in the 10%
  sample moved 0.19×–1× with identical logic after its upstream table's physical order changed (s08).

## Details and evidence

The evidence for each row is in `RESULTS.md` (lab), `PLATFORM_FEASIBILITY.md` and the research notes
(documented). The rows that most affect the decision:

- **Scale transfer (27) and data growth (11).** The key question is whether *any* cheap CI data
  (samples, time windows, static plans) predicts production-scale impact across change classes. See
  E1. If it does not, CI cost is tied to production cost (H5).
- **Shared / prepaid capacity (3, 6, 7).** The number a PR comment shows depends on a
  *definition*: attributed or marginal, short-run or long-run. The lab (E2) shows the same measured
  change priced very differently under different pools. This is a product-policy decision plus
  customer configuration. The engine cannot learn it from telemetry.
- **Frequency (13, 17, 21, 22).** Recurring $ = per-run Δ × future frequency. Frequency is exact for
  cron jobs, noisy for BI traffic, and unforecastable for seasonal or ad hoc work (E6, simulated).
- **Materialisation and consumers (20).** Getting the sign right requires knowing who reads a
  relation. That exists only as platform access/lineage telemetry, not in dbt.
