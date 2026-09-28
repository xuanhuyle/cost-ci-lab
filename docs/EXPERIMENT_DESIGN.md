# Experiment design

What was built, what each experiment tries to falsify, and how to reproduce it. Results are in
[`RESULTS.md`](RESULTS.md).

## 0. Why a local lab, and what it can and cannot prove

No Snowflake, Databricks or BigQuery credentials were provided for this investigation (see
[`OWNER_REQUEST.md`](OWNER_REQUEST.md)). Every executable experiment therefore runs in a **local lab**:
- **Engine:** DuckDB 1.5.5 with 4 threads and a 3 GB memory limit, standing in for a fixed-size
  warehouse.
- **dbt:** real dbt-core 1.12.5 with dbt-duckdb 1.11, used for parsing, `state:modified`, lineage and
  `--defer` compilation.
- **Data:** TPC-H.

**What the lab can establish (`MEASURED (local engine)`):** whether *measurement strategies* (static
plans, byte counts, samples, full clones, history anchoring) recover the production-scale resource
impact of real SQL/dbt changes. It can also show:
- how noisy repeated execution is;
- where scale transfer breaks;
- what dbt's change detection sees and misses;
- how CI analysis cost compares with the impact it detects.

**What it cannot establish:** how Snowflake, Databricks or BigQuery behave, or whether their bills
would be predicted accurately. Where lab results are extrapolated to a platform they are labelled
`INFERRED`. The dollar layer applies *documented* billing rules to *synthetic* production months, so
it is labelled `SIMULATED`: it demonstrates mechanisms, not magnitudes.

## 1. Hypotheses → experiments

| Hypothesis | Experiment | Output |
|---|---|---|
| H1 attribution: diff → models → workloads → history | E1: dbt state + consumer mapping over 25 PRs | per-scenario detected vs affected workloads |
| H2 counterfactual: Cost(PR) − Cost(MAIN) | E1: MAIN vs PR at production scale = truth; CI strategies = estimates | `results/bench/*.json`, `results/analysis.json` |
| H3 production extrapolation (per-run → monthly $) | E1 (history anchoring), E2 (pool economics), E6 (frequency) | `analysis.json`, `economics.json`, `frequency.json` |
| H4 calibration | E7: leave-one-out correction on predicted vs realised pairs | `calibration.json` |
| H5 CI practicality | E1 timings + CI cost accounting (lab-seconds per strategy vs monthly impact) | `analysis.json` |
| H6 cross-platform abstraction | E2 (the same measured changes under 7 pool/billing configurations) + adapter design | `economics.json`, `ARCHITECTURE.md` |
| HA vs HB: cheap measurements transfer vs are scale-dependent | E1 (samples, two-point extrapolation, static) + E3 (warehouse size, concurrency, cold cache) | `analysis.json`, `transfer.json` |
| HC vs HD: attributed ≈ marginal vs pool-dependent | E2 | `economics.json` |
| Downstream propagation (Phase 9) | E4 | `downstream.json` |
| Uncertainty grounding (Phase 7) | E5 | `uncertainty.json` |

## 2. The lab

**Data environments** (`python -m costci.data --sf 2`; deterministic):

| env | contents | role |
|---|---|---|
| prod | TPC-H SF2: 12.0M lineitem, 3.0M orders, 300k customers. `lineitem` is sorted by ship date and `orders` by order date, so zone-map pruning behaves like partition/micro-partition pruning. | production, and also the "full zero-copy clone" CI option |
| bern01 | 1% Bernoulli sample of every large table, independently | naive `TABLESAMPLE`-style CI data |
| key01 / key10 | 1% / 10% of customers with all their orders and line items; dimensions whole | key-consistent sampling |
| recent90 | fact tables filtered to their last 90 days; dimensions whole | the common dbt "limit data in CI" pattern |

**dbt project** (`benchmark/project`), 17 models:
- 5 staging views;
- the `int_order_lines`, `customer_features` and `part_supplier_costs` tables;
- the `fct_daily_revenue` incremental model (delete+insert, 3-day lookback);
- 5 mart tables and 2 report views.

It has two macros (`net_revenue`, `run_date_minus`). The SQL is adapter-portable (dbt
cross-database macros), so the same project can run against Snowflake's `SNOWFLAKE_SAMPLE_DATA.TPCH_SF*`.

**Production context** (`benchmark/production_context.yaml`; all `ASSUMED`):
- Jobs: a daily build (30/month), an hourly incremental revenue job (720/month) and a monthly LTV job
  (1/month).
- Four BI consumers reading dbt relations, at 60k, 30k, 9k and 3k queries per month.
- Two capacity pools: a transform warehouse and a BI warehouse.
- `time_scale = data_scale = 100` converts lab units to "production" units, for the dollar layer only.

**Harness:**
- `costci/scenario.py`:
  - builds the MAIN and PR project copies;
  - asks dbt for `state:modified`, its six sub-selectors, and `state:modified+`;
  - maps changed relations to jobs and BI consumers;
  - compiles both sides with `--defer` against prod.

  It stages placeholder relations so that compile resolves refs the way `dbt build` would (E-003).
  Incremental models therefore compile in their *incremental* branch, as after a `dbt clone`.
- `costci/execute.py` emulates dbt materialisations and profiles every statement: wall latency,
  operator CPU, rows scanned, peak memory and spill. It also computes "logical bytes", which emulate
  BigQuery on-demand semantics: rows scanned after pruning × logical width of every referenced column.

## 3. Benchmark suite (25 PRs)

Each scenario is an overlay on the base project (`benchmark/scenarios/<id>/`). Scenario files hold
**no expected outputs**. The label column is descriptive and is never used for scoring.

| id | change (the PR) | label | what it is designed to test |
|---|---|---|---|
| s01 | Widen int_order_lines analysis window from 180 to 730 days (`models/intermediate/int_order_lines.sql`) | regression | Hard-codes a 2-year window. More rows scanned, joined and materialised; downstream marts read a bigger table. |
| s02 | Compare ship_date as strings (same result, defeats pruning) (`models/intermediate/int_order_lines.sql`) | regression | Semantically equivalent filter, but wrapping the clustering column in a cast prevents zone-map / partition pruning. Magnitude depends on physical layout. |
| s03 | Reprocess 45 days instead of 3 on every incremental run (`models/marts/fct_daily_revenue.sql`) | regression | Lookback widened in SQL to capture late-arriving returns. The hourly job reprocesses 15x more days. |
| s04 | Switch fct_daily_revenue from incremental to full table rebuild (`models/marts/fct_daily_revenue.sql`) | regression | Removes incremental logic "to simplify"; every hourly run now rebuilds all history. |
| s05 | Join part suppliers on part_key only (many-to-many fan-out) (`models/marts/mart_part_profitability.sql`) | regression | Adds average supplier cost by joining stg_partsupp on part_key alone; every order line fans out to all suppliers of the part. |
| s06 | Self-join order lines on (ship_date, ship_mode) to count peer volume (`models/marts/mart_part_profitability.sql`) | adversarial | Join on a low-cardinality key. Output grows with the square of rows per group, so cost grows super-linearly with data volume; small samples understate it. |
| s07 | Add SELECT DISTINCT over a wide, already-unique row set (`models/intermediate/int_order_lines.sql`) | regression | Defensive DISTINCT across 16 columns including long comment strings. Same bytes scanned, extra hashing/memory. |
| s08 | Add per-customer window functions (lag, running sum, percent_rank) (`models/intermediate/customer_features.sql`) | regression | Compute-bound change that sorts every order within customer. Bytes scanned unchanged, so byte-based estimators see nothing. |
| s09 | Split customer_features into three separately-scanned CTEs (`models/intermediate/customer_features.sql`) | regression | A "readability" refactor that scans orders three times and adds two joins. |
| s10 | Materialise dim_customers as a view instead of a table (`models/marts/dim_customers.sql`) | adversarial | Build cost disappears from the daily job, but every BI query and downstream model now recomputes the join. DAG-only estimators see a saving. |
| s11 | Materialise rpt_customer_segments as a table (`models/reports/rpt_customer_segments.sql`) | improvement | Adds a small daily build and removes the aggregation from 9,000 dashboard queries per month. DAG-only estimators see only the added build. |
| s12 | Move the recent-months filter from HAVING into WHERE (`models/marts/mart_revenue_by_nation.sql`) | ambiguous | Hand-written predicate pushdown. Whether it saves anything depends on whether the optimiser already pushed the HAVING filter down. |
| s13 | Drop the two free-text comment columns from int_order_lines (`models/intermediate/int_order_lines.sql`) | improvement | Stops carrying long strings. Large reduction in bytes read/written, smaller reduction in compute. |
| s14 | Pre-aggregate line items per order before joining to orders (`models/marts/customer_ltv_monthly.sql`) | improvement | Classic join optimisation in the monthly LTV job: fewer rows through the join and the distinct count. |
| s15 | Stop excluding returned items from int_order_lines (`models/intermediate/int_order_lines.sql`) | regression | Direct model cost barely changes (same scan), but it emits ~1/3 more rows, so unchanged downstream marts get more expensive. Tests downstream propagation. |
| s16 | Add a new daily churn mart (`models/marts/mart_customer_churn.sql`) | regression | Pure addition: there is no MAIN baseline, so ratio-based estimators cannot be anchored. |
| s17 | Add rolling windows, ranks and medians to the monthly LTV job (`models/marts/customer_ltv_monthly.sql`) | regression | Large per-run increase in an infrequent (monthly) job. Per-run and monthly materiality disagree. |
| s18 | Add 28-day average and year-over-year join to the KPI view (`models/reports/rpt_daily_kpis.sql`) | regression | Each dashboard query is individually cheap, but the view is queried 30,000 times a month on the BI warehouse. |
| s19 | Same KPI-view change as s18, on an always-on BI warehouse with spare capacity (`models/reports/rpt_daily_kpis.sql`) | adversarial | Runtime per query rises exactly as in s18, but the BI warehouse never suspends, so marginal spend is ~zero until capacity saturates. Context override: `pools.bi_wh.auto_suspend_s=null`. |
| s20 | Carry six more columns through int_order_lines, on prepaid capacity (`models/intermediate/int_order_lines.sql`) | adversarial | More bytes read and written, little extra compute. Under on-demand byte pricing spend rises; under prepaid slot/credit capacity with headroom it barely moves. Context override: `pools.transform_wh.kind=bigquery_editions`. |
| s21 | Reformat customer_features, rename CTE, add comments (`models/intermediate/customer_features.sql`) | neutral | No semantic change. dbt flags the model (and its descendants) as modified because the raw SQL text changed. Tests false positives. |
| s22 | Add a full ORDER BY to int_order_lines "for deterministic output" (`models/intermediate/int_order_lines.sql`) | regression | Memory-hungry sort of a wide table. Used for the concurrency sub-experiment (isolated CI run vs production under memory/CPU contention). |
| s23 | Round and null-guard the shared net_revenue macro (`macros/net_revenue.sql`) | neutral | One macro edit silently changes every model that uses it, and their descendants. Cheap arithmetic; tests multi-model attribution and false positives. |
| s24 | Change the revenue_lookback_days var default from 3 to 45 in dbt_project.yml (`dbt_project.yml`) | adversarial | Same production effect as s03, but the change lives in project config, not in the model file. Tests whether change detection sees it. |
| s25 | Materialise the whole staging layer as tables (folder-level config) (`dbt_project.yml`) | regression | One line in dbt_project.yml turns five staging views into tables rebuilt daily (copies of the largest source tables). |

How the suite covers the brief's scenario list:

| Brief item | Scenario(s) |
|---|---|
| widen a date filter | s01 |
| remove partition pruning | s02 |
| expand an incremental window | s03, s24 |
| incremental → full refresh | s04 |
| many-to-many join | s05 |
| increase join cardinality | s06 |
| unnecessary DISTINCT | s07 |
| expensive window functions | s08, s17 |
| repeated scans | s09 |
| table ↔ view | s10, s11 |
| predicate pushdown | s12 |
| select fewer columns | s13 |
| join optimisation | s14 |
| increased downstream rows | s15 |
| new downstream dependency | s16 |
| infrequent but expensive | s17 |
| frequent but cheap | s18 |

Cases aimed at naive estimators:

| Naive-estimator breaker | Where tested |
|---|---|
| runtime up, $ flat | s19 |
| bytes up, spend flat | s20 |
| cosmetic change / cache bust | s21 |
| concurrency | s22 + E3 |
| macro fan-out | s23 |
| config/var changes invisible to naive diffing | s24, s25 |
| upstream rows → downstream cost | s15, s01 |
| sparse/seasonal frequency | E6 |
| shared compute / idle capacity | E2 |

## 4. Measurement protocol and ground truth

For every scenario and environment, MAIN and PR run in separate schemas (`ci_main`, `ci_pr`).
Unmodified upstream is deferred to that environment's `prod` schema, and incremental targets are
cloned first. Within a scenario:
- rep 0 is a warm-up and is discarded;
- reps 1..N are *interleaved* with alternating order (MAIN→PR, PR→MAIN) to cancel drift and
  cache-order bias;
- within a rep, every workload of a variant runs in dependency order.

The prod environment runs 8 reps, assigned to disjoint roles so that the noise in each role is
independent:

| rep | role |
|---|---|
| 1 | the **CI full-clone A/B** measurement (one run each of MAIN and PR) |
| 2–4 (MAIN only) | **production history** of the current code (the anchor) |
| 5–8 | **ground truth**: median per workload and variant |

Sample environments run 3 reps. Static `EXPLAIN` plans are captured after the warm-up.

**Truth for a scenario** is Δ = Σ_w runs_w · (median_PR,w − median_MAIN,w), summed over every
affected workload (models in `state:modified+` plus consumers of those relations), in
workload-seconds per month. The relative impact is rel = Δ / Σ_w runs_w · median_MAIN,w. A new
workload has no MAIN cost, so rel = +∞, which counts as a large regression.

## 5. Estimators (Phase 5)

Every estimator uses only information that would be available before merge:

| key | strategy class | information used | CI execution |
|---|---|---|---|
| static_cout | A: static / plan | `EXPLAIN` estimated cardinalities (C_out = Σ operator estimates) as a ratio × history. For new models, seconds-per-C_out is fitted on history. | none |
| bytes_proxy | D: native-estimator analog | logical bytes as a ratio × history. These approximate BigQuery dry-run semantics; here they are the *exact* post-pruning bytes, so an upper bound on what a dry run could provide. | none on BigQuery (dry run is free) |
| ab_full_abs | B: controlled A/B | one MAIN and one PR run on the full clone; absolute Δ | 2 × production run |
| ab_full_anchored | B+C | the same ratio applied to MAIN's production history | 2 × production run |
| pr_vs_history | C | one PR run on the full clone minus MAIN's production history | 1 × production run |
| ab_bern01 / ab_key01 / ab_key10 / ab_recent90 | B-sample + C | sample-env ratio × history (linear scale-up for new models) | 2 × sample run |
| ab_two_point | E component | power law fitted through key01 and key10 per variant, extrapolated to full scale | key01 + key10 |
| hybrid | E | Three stages (below) | adaptive |

The hybrid's three stages:
1. **Static screen.** Identical plan shape and ≤5% change in C_out and bytes ⇒ "no change", with no
   execution.
2. **Key-consistent samples** with two-point extrapolation.
3. **Escalate to a full-clone A/B** when any of these holds:
   - superlinearity is detected (PR scaling exponent minus MAIN's > 0.15);
   - the sample ratios disagree by more than 1.5×;
   - the predicted change exceeds 25%;
   - the workload is new.

**Downstream mapping levels** (Phase 9) are applied to ab_full_anchored:
- `direct`: modified models only;
- `plus_1hop`: modified models plus their direct children;
- `all_models`: dbt's `state:modified+`;
- `all_with_consumers`: all models plus their consumers (the default).

## 6. Metrics (Phase 6) and why these thresholds

- **Materiality threshold: 10%** of the affected workloads' monthly cost. This was chosen from the
  measured noise floor (E-009: 5–29% CV per single run). Below about 10%, even 4-rep truth medians
  do not reliably get the sign right.
- **Direction accuracy on material changes:** whether the class (increase / decrease / immaterial)
  is correct.
- **Large-regression recall:** for changes whose truth is ≥ +50%. "Recall" means the estimator
  warned (estimate ≥ +10%); "strict" recall means its estimate was itself ≥ +50%.
- **False-warning rate:** the share of truly immaterial changes flagged as material.
- **Magnitude bucket:** exact match, or within one bucket, across 9 signed buckets
  (±10 / 25 / 50 / 100%).
- **Magnitude error:** median |log(estimate/truth)| over material, same-sign cases.
- **Ranking:** Spearman correlation of the monthly Δ across scenarios.
- **CI cost:** lab-seconds executed per strategy, relative to the monthly production cost of the
  affected workloads.
- **CI latency:** wall time of the dbt and execution steps.

## 7. Supplementary experiments

| id | name | what varies | status |
|---|---|---|---|
| E2 | economics | Each scenario is billed under 7 pool configurations: its own context; Snowflake dedicated; Snowflake always-on BI; attributed per-second; BigQuery on-demand; BigQuery editions; Databricks serverless SQL. Compared: truth marginal vs naive attributed vs estimated marginal. | SIMULATED month, DOCUMENTED rules, ASSUMED unit scaling |
| E3 | transfer | CI at 1 thread vs production at 4 threads; production under concurrent background load in the same engine; cold single run without warm-up | MEASURED (local) |
| E4 | downstream | Cost of executing direct / +1 hop / all descendants; row-count elasticity propagation | MEASURED (local) |
| E5 | uncertainty | 80% intervals from the measured noise model; coverage; confidence labels vs correctness | MEASURED noise, computed intervals |
| E6 | frequency | Synthetic run histories (cron, BI weekday, growth, seasonal, sparse, data-driven) → next-month forecast error | SIMULATED |
| E7 | calibration | Leave-one-scenario-out multiplicative corrections (global, and per workload class) | MEASURED pairs, local only |

## 8. Threats to validity

- **One engine, one schema, one machine.** The scale is small (SF2), and laptop noise is higher
  than a dedicated warehouse's. DuckDB's optimiser is not Snowflake's. In particular, DuckDB
  `EXPLAIN` exposes cardinality estimates that Snowflake's does not, so the static estimator is
  *better* informed here than it would be on Snowflake.
- **The lab's full clone *is* the production data.** The full-clone A/B's residual error is
  therefore noise and nothing else. Real CI clones differ from future production through data
  growth, concurrency, cache warmth and warehouse size; E3 measures some of these separately.
- **Synthetic production context.** Schedules, BI volumes, pools and κ are illustrative. Dollar
  magnitudes in E2 must not be read as forecasts.
- **Hand-written scenarios.** The investigator wrote them to cover the brief's list, so they are not
  a random sample of real PRs. Rates such as "% of PRs that are immaterial" are not population
  estimates.

## 9. Reproduce

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m costci.data --sf 2
.venv/Scripts/python -m experiments.run_benchmark
.venv/Scripts/python -m experiments.measure_baseline
.venv/Scripts/python -m experiments.analyze
.venv/Scripts/python -m experiments.economics_run
.venv/Scripts/python -m experiments.transfer
.venv/Scripts/python -m experiments.downstream
.venv/Scripts/python -m experiments.uncertainty
.venv/Scripts/python -m experiments.frequency
.venv/Scripts/python -m experiments.calibration
.venv/Scripts/python -m pytest -q
```

On Linux/macOS, use `.venv/bin/` instead of `.venv/Scripts/`. `costci.data` takes about 2 min and
~1.5 GB of disk. `run_benchmark` takes about 75 min on a 4-core laptop.
