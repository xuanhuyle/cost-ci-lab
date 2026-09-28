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
   The measurement layer is therefore mandatory for time-billed platforms, and its cost scales with
   the production cost of the affected workloads. The strategy policy (component 3) exists to spend
   that budget only where needed. It is a *cost-control* component, not an accuracy component.
2. **Static plans and bytes are screening signals, not estimators.** They are used only to skip
   execution for changes proven to have unchanged plans. They are never used for magnitude.
3. **Consumer discovery is not optional.** Materialisation changes move cost between the dbt DAG and
   its consumers, so a DAG-only system gets the sign wrong.
4. **Economic translation is a pool replay with explicit customer configuration:** commitments,
   negotiated prices, and the marginal-vs-attributed policy. Reporting must say which view the
   number is.
5. **Calibration works on usage ratios (weeks), not dollars (months).** Dollar-level ground truth is
   confounded by other changes landing in the same pool.
