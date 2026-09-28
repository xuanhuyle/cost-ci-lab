# Architecture: is "cost impact of a software change" a real, platform-independent object?

Phase 2 deliverable. It was drafted after the platform research and revised after the lab results
(`RESULTS.md`). Evidence labels are as in `CLAUDE.md`.

## 1. Answer first

**The *decision object* is platform-independent. The *measurement* and the *economics* are not.**

What survives across Snowflake, Databricks and BigQuery:

```text
CostImpact(change, context) =
    Σ_pools [ Bill_p( month of executions on pool p with PR usage )
            − Bill_p( month of executions on pool p with MAIN usage ) ]
  with   usage_w(PR) = usage_w(MAIN) × ratio_w      for each affected workload w
  and    an interval, a confidence grade, and the drivers (which workloads, which pools)
```

Three parts of this object are not portable:
- **What "usage" is**, in native units: warehouse-seconds at a size, logical bytes, *allocated*
  slot-seconds, or DBU-hours plus VM-hours.
- **How the per-workload ratio can be obtained before merge.** A free dry run works only for
  BigQuery on-demand bytes. Everything else needs execution or history (`DOCUMENTED`, E-010/E-015/E-016).
- **`Bill_p`**, the pool's billing function. Examples: Snowflake warehouse uptime with a 60 s minimum
  and auto-suspend; BigQuery's allocated slots in 50-slot, ≥60 s steps; Databricks DBUs per
  warehouse-hour plus cloud VM for classic compute.

**What fails as an abstraction is "cost per query × frequency".** On any shared, provisioned or
prepaid pool, the per-query number is an *allocation*: Snowflake's `QUERY_ATTRIBUTION_HISTORY`
excludes idle time, Databricks has no per-query cost, and BigQuery editions has no per-job $. The
marginal dollar can be 0 on an always-on pool with headroom, or a step function when scale-out is
triggered. Experiment E2 shows the same measured change priced differently by pool type (`SIMULATED`
under `DOCUMENTED` rules). So the brief's `CostImpact(code_change, production_context)` is sound
**only if `production_context` explicitly contains the capacity pools, their billing functions and
their background load**. Without that it is misleading on exactly the platforms where most spend
sits.

## 2. The proposed `CostProvider` interface, method by method

| Brief method | Verdict | Why (evidence) |
|---|---|---|
| `identify_affected_workloads(change)` | **Split.** A platform-independent core plus provider consumer discovery. | dbt lineage (`state:modified+`) is the same on every adapter. Consumers outside dbt (BI, apps) come from `ACCESS_HISTORY` / `JOBS.referenced_tables` / `table_lineage`. s10/s11 show that ignoring consumers flips the sign of the verdict. `state:modified` must be complemented by a rendered-SQL diff (E-017; s24). |
| `get_production_baseline(workload)` | **Keep**, but in native usage units with a distribution, not dollars | Per-run usage is directly measured on all three platforms. Per-run *dollars* are an allocation (§1). |
| `prepare_candidate_environment(change)` | **Keep** as `clone_for_ci` + defer | Zero-copy clone (Snowflake), shallow clone (Databricks), table clone (BigQuery), with `dbt clone` for incremental targets. The lab reproduces the incremental-branch subtlety (E-003). |
| `execute_baseline` / `execute_candidate` | **Merge into one `run(workload, strategy)`** chosen by a policy. The baseline can come from history instead of a second execution. | The best cheap estimator is PR-vs-history (one execution), when CI and production conditions match. The policy (static screen → samples → full clone) is platform-independent; only `run` is not. |
| `collect_resource_usage(run)` | **Fold into `run`**, read synchronously from real-time metrics | Billing and attribution views lag 3–24 h (Snowflake attribution 8 h; Databricks billing ≤12–24 h), which is useless for a CI verdict. Real-time execution metrics exist on all three. |
| `get_historical_frequency(workload)` | **Keep** as `run_timestamps`; the frequency *model* is platform-independent | Counts per query hash / job run are available everywhere. Forecasting them is the hard part (E6). |
| `get_historical_cost(workload)` | **Drop** as a provider primitive | Replace with `pool_timeline` + `billing_model`: price the pool, not the query. |
| `estimate_recurring_delta(...)` | **Move out of the provider** into the engine | Replay the month on each pool with PR vs MAIN usage. Same code for every platform; only `Bill_p` differs. |
| `validate_realised_cost(...)` | **Keep**, but validate per-run *usage* first and pool $ second | Usage is available within ~1 h; $ within 3–24 h. Usage-level calibration isolates estimator error from billing/attribution error. |
| *(missing)* `billing_model(pool)`, `effective_price(pool)` | **Add** | The economic translation is a pool property. The negotiated price is invisible on Databricks and org-role-gated on Snowflake (E-014, E-011), so it becomes customer configuration. |
| *(missing)* uncertainty | **Add** as a first-class engine output | Noise (E-009), scale transfer, frequency and attribution each contribute. Intervals must be computed, not asserted (E5). |

The revised interface is `costci/providers.py`. It has three platform services, `Measurement`,
`Telemetry` and `Billing`, and a `CAPABILITIES` matrix that maps every method to each platform's
documented primitive and its Phase-1 classification. Tests (`tests/test_providers.py`) enforce that
matrix.

## 3. Components (the separation the brief asks for)

```text
 PR (git diff) ─► [1 change detection] ─► [2 workload mapping] ─► [3 strategy policy]
                     dbt state:modified      dbt DAG + consumers      static → sample → clone
                     + rendered-SQL diff     + jobs/schedules
                                                                         │
     production ◄── [4 provider telemetry] ──────────────┐               ▼
     platform        history, timestamps, pool timeline  │    [5 provider measurement]
                                                         │      run / explain / dry run
                                                         ▼               │
                                              [6 normalisation] ◄────────┘
                                               native usage per run, ratios, provenance
                                                         │
                                              [7 recurring extrapolation]
                                               frequency model × pool replay (Bill_p)
                                                         │
                                              [8 uncertainty & confidence]
                                                         │
                                              [9 CI presentation] ─► PR comment / gate
                                                         │
            post-merge telemetry ─► [10 calibration] ────┘ (per workload / class / pool)
```

| # | Component | Platform-specific? | Implemented here | Evidence it is needed |
|---|---|---|---|---|
| 1 | Change detection | No (dbt), plus the provider for compile-time introspection | `costci/scenario.py` (dbt state + git diff) | s21 (cosmetic false positive), s23 (macro fan-out), s24 (var change), s25 (config inheritance) |
| 2 | Workload mapping | Partly: consumer discovery and schedules come from the provider | dbt `state:modified+` + consumer registry | s10/s11 (consumers flip the sign), s15 (downstream) |
| 3 | Strategy policy | No | `hybrid` in `experiments/analyze.py` | E1: which cheap strategies can be trusted when |
| 4 | Telemetry | Yes | `CAPABILITIES`; lab uses measured history | E-012, E-013, E-015 |
| 5 | Measurement | Yes | `costci/execute.py` (DuckDB); `live/snowflake/adapter.py` (UNVALIDATED) | E-010 (no pre-execution estimates) |
| 6 | Normalisation | Partly: units differ | `costci/execute.py` (latency, CPU, logical bytes) | s02, s08, s13 (bytes vs compute disagree) |
| 7 | Recurring extrapolation | Billing functions are platform-specific; the replay engine is not | `costci/economics.py`, `costci/pools.py` | E2, E6 |
| 8 | Uncertainty | No | `experiments/uncertainty.py` | E5 |
| 9 | CI presentation | No | not built (commodity; out of scope until the primitive works) | — |
| 10 | Calibration | No, given telemetry | `experiments/calibration.py` | E7 |

## 4. Data model (minimal)

```text
Workload     id, kind (dbt node | consumer query), relations, job | consumer, pool, schedule
ChangeSet    changed files, modified nodes (+ reason: body/config/macro/rendered-only), new, removed
Usage        workload, seconds, native units {bytes, slot_s, credits, dbu}, conditions
             {env, warehouse size, cache warmth, concurrency}, provenance {MEASURED|DERIVED|ESTIMATED}
Pool         kind + billing params (size, auto_suspend, clusters | baseline/max slots | $/TiB),
             effective price source, background timeline
Prediction   per workload: ratio distribution + strategy + CI cost; per pool: Δ$ distribution;
             total interval, confidence grade, top drivers, assumptions
Realisation  per workload post-merge usage; per pool metered $; linked to Prediction for calibration
```

## 5. What the results changed in this architecture

These are the design consequences of `RESULTS.md`:

1. **Execution at production scale is the only strategy that tracked truth across change classes.**
   Full-clone A/B: 100% direction on material changes, 0 wrong-sign errors (E1). Every cheaper
   estimator made wrong-sign or missed-material errors.
   - The measurement layer is therefore mandatory for time-billed platforms, and its cost scales
     with the production cost of the affected workloads (k ≈ 2.5–4.6 production runs per analysis).
   - The strategy policy (component 3) exists to spend that budget only where needed. It is a
     *cost-control* component, not an accuracy component.
2. **Static plans and bytes are screening signals, not estimators.**
   - They skip execution only for workloads proven to have unchanged plans. That resolved 58 of 108
     workload-analyses in E1, mostly unchanged descendants.
   - They are never used for magnitude: static C_out has 20% of estimates within 2×, and bytes are
     blind to compute-bound changes (s17).
3. **Consumer discovery is not optional.** Materialisation changes move cost between the dbt DAG and
   its consumers. DAG-only mapping scored 75% direction vs 100% with consumers, and got the sign
   wrong on s10.
4. **Measurement must be noise-adaptive.** Millisecond statements weighted by high frequency must be
   repeated until stable (E-030). Paired A/B beats comparing against history when drift is possible
   (s04).
5. **Economic translation is a pool replay with explicit customer configuration:** commitments,
   negotiated prices, and the marginal-vs-attributed policy. Reporting must say which view the
   number is; E2 shows sign flips between the two views.
6. **Calibration works on usage ratios (weeks), not dollars (months).** Dollar-level ground truth is
   confounded by other changes landing in the same pool. It removes small systematic bias from an
   accurate estimator, but cannot rescue an inaccurate one (E7).

## 6. Post-merge calibration loop (Phase 10)

```text
PR analysed ─► Prediction stored (per workload: CI ratio, strategy, conditions; per pool: Δ$ range)
     │
merge + deploy ─► first N production runs of each affected workload (query tag / job run id)
     │
realised per-run usage (≤1 h: Snowflake QUERY_HISTORY 45 min, Databricks query history, BigQuery JOBS)
     │
realised pool $ (3–24 h: WAREHOUSE_METERING_HISTORY, system.billing.usage, RESERVATIONS_TIMELINE)
     │
error = log(realised ratio / predicted ratio)  per workload  ─►  corrections + noise-model update
```

What each level can reasonably calibrate:

| Level | Calibratable? | Signal | Why |
|---|---|---|---|
| Per workload | **Yes** | Each merged PR touching it yields one (predicted, realised) pair. Its run history continuously updates its noise model. | Recurring workloads repeat (E-020: most warehouse queries are repeats). Noise and CI-vs-production transfer are workload properties. |
| Per warehouse / pool | **Yes** | Every PR landing on the pool; metering vs replayed bill | CI-vs-production condition gaps (size, concurrency, cache) and billing-model fidelity are pool properties |
| Per workload class (materialisation, change type) | Weakly | Small-n groups | The lab shows class-level biases for cheap strategies, but sign errors are scenario-specific and cannot be corrected by a factor (E7) |
| Per repository / customer | As aggregates of the above | — | No new signal beyond workloads and pools |
| Per provider, cross-customer | **No claim** | — | No evidence of a transferable signal. It cannot be tested without multi-customer data, and the mechanisms observed (layout, data distribution, pool load) are customer-specific |

Design rule: calibrate the *ratio* (usage) and the *pool replay* separately. A dollar-level residual
mixes estimator error, billing-model error and unrelated changes that landed in the same pool.

## 7. Portability (Phase 12): which workload families can a common product support?

**Grading.** "Estimate quality" means the quality of a pre-merge **monthly-$** estimate that is
decision-useful. Usage deltas can usually be measured on every family below; what varies is whether
they can be turned into trustworthy dollars in CI time.
- A grade needs three things: a CI execution path, a per-run attribution path, and a
  billing-function path.
- Grades combine documented platform primitives (`PLATFORM_FEASIBILITY.md`) with lab mechanisms
  (`RESULTS.md`).
- They are `INFERRED`. None was validated on a live platform.

| Platform | Workload family | Grade | Why |
|---|---|---|---|
| Snowflake | dbt SQL models on a **dedicated** warehouse, run frequently enough to pay for the check (E10: break-even ~40–70 runs/month at median assumptions) | **HIGH** | Zero-copy clone + `--defer` + `dbt clone` for incremental targets; real-time `execution_time`; the billing function is fully documented and replayable (uptime, 60 s minimum, auto-suspend) |
| Snowflake | dbt models on a warehouse **shared** with other teams | MEDIUM | The usage delta is measurable; marginal $ depends on the pool's background load (replayable from `QUERY_HISTORY` / `WAREHOUSE_EVENTS_HISTORY`); attribution is an allocation that excludes idle time |
| Snowflake | BI / consumer queries on busy BI warehouses | LOW for $ (MEDIUM for usage) | Changes are absorbed by uptime that is already paid for, until multi-cluster scale-out, whose timing is not published |
| Snowflake | Adaptive warehouses (GA 2026-06) | MEDIUM | Per-query credits are metered (`QUERY_METERING_HISTORY`, ≤1 h), so attribution ≈ marginal. But no formula is published: a CI run's credits are observable ~1 h after it, not at once |
| Snowflake | Serverless features: auto-clustering, MVs, dynamic tables, serverless tasks | LOW / NOT_VIABLE | Outside query attribution; the vendor's own estimators are ±50–100%; refresh work depends on the data |
| Databricks | dbt SQL on a **dedicated serverless SQL warehouse** | MEDIUM | Task time is available in near real time (Query History API); billing is at warehouse × hour grain, so per-query $ is apportioned; negotiated prices are invisible |
| Databricks | Serverless jobs / dbt tasks on job compute | MEDIUM | DBUs per `job_run_id` are native. Billing latency of up to 24 h makes the CI verdict depend on execution metrics, not DBUs. Performance mode changes DBUs |
| Databricks | Classic job clusters | LOW–MEDIUM | DBUs per run exist, but VM, disk and network cost is billed by the cloud provider (a join via tags); spot, autoscaling and startup add noise |
| Databricks | Shared all-purpose clusters | **NOT_VIABLE** | Docs: per-job cost cannot be exact; `run_as` is the cluster creator; many tenants |
| Databricks | Non-SQL Spark (Python/Scala) | LOW | No `query.history` rows on classic compute; execution is the only estimator; attribution only through job-scoped compute |
| BigQuery | Any query or dbt model under **on-demand** pricing | **HIGH** (already commodity) | Dry-run bytes ≈ the bill, with upper-bound caveats for clustered tables and scripts; `dbt-costgate` already does this |
| BigQuery | Editions, autoscale-only reservation | MEDIUM | Slot-ms is noisy and billed as allocated 50-slot/60 s steps; replayable from `RESERVATIONS_TIMELINE` |
| BigQuery | Editions with baseline / commitments shared across teams | LOW | Marginal $ is 0 until saturation, then a step; per-job $ does not exist |

**Verdict on a common commercial product.**
- A single product *can* span the HIGH and MEDIUM families on all three platforms with one engine:
  change detection, workload mapping, the strategy policy, pool replay, uncertainty and calibration.
  It needs three thin platform adapters (measurement, telemetry, billing).
- The product's *reliable* region is small: dedicated or per-query-billed compute running scheduled
  SQL. Everything shared, prepaid or non-SQL degrades to "usage delta plus an explicitly
  policy-dependent $ range".
- Databricks is the least favourable of the three for a synchronous CI verdict. Billing latency is
  up to 24 h, the disk cache cannot be disabled, VM cost sits outside the Databricks bill, and
  negotiated prices are invisible.
