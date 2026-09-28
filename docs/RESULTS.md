# Results

<!-- Sections marked [FILL] are completed from results/tables/*.md after all runs finish. -->

## 0. How to read this document (evidence separation)

| Section | Evidence level | What it is |
|---|---|---|
| **A. Live platform results** | — | **None.** No Snowflake, Databricks or BigQuery credentials were available (`OWNER_REQUEST.md`). Nothing below is a measurement of a real warehouse. |
| **B. Local measured results** | `MEASURED (local engine)` | DuckDB 1.5.5 + real dbt-core 1.12.5 on TPC-H SF2 (E1, E3, E4, E8, E9, noise). Valid statements about *strategies* on *this engine*. Transfer to Snowflake/Databricks/BigQuery is `INFERRED` only. |
| **C. Computed from local measurements** | `MEASURED` inputs + stated method | Uncertainty intervals (E5), calibration (E7), CI-cost break-even (E10, with ASSUMED regression rates). |
| **D. Simulated** | `SIMULATED` under `DOCUMENTED` rules | Pool economics on a synthetic month (E2), frequency extrapolation on synthetic histories (E6). They illustrate mechanisms; they are not forecasts. |
| **E. Documented platform facts** | `DOCUMENTED` | `PLATFORM_FEASIBILITY.md`, `EVIDENCE_LOG.md` E-010…E-022. |

## 1. Viability bars: refined before judging

The brief's provisional bars were: >90% direction on material changes, >90% recall on large (>50%)
regressions, a low false-positive rate, useful magnitude buckets, and a cheap, fast check. Before
judging against them, the lab showed three problems with the bars as written.

1. **"Material" must be defined relative to the measurement noise floor.** Single-run CV is
   5–29% for 0.2–10 s statements (E-009). A few scenarios have a truth that changes class across
   repetitions when it sits near ±10% (E1 truth stability). We keep **10%** as the materiality
   threshold. We also score separately on scenarios whose truth class is stable, and treat 10–25% as
   a gray zone.
2. **"Material" has two denominators.**
   - *Relative to the affected workloads* (the PR comment's "+Y%").
   - *Relative to the whole bill* (economic materiality).

   A 4.5× regression in a model that is 2% of a busy affected set is +9% of that set (s08). We
   report both: rel ≥ 10% of the affected workloads, and ≥ 1% of the total production bill.
3. **"Cheap and fast enough" needs a denominator too.** We express CI cost as production-run
   equivalents per analysis (k, **measured**), and as a break-even run frequency against the risk it
   removes (E10).

Refined bars used in `DECISION.md`:

| Bar | Threshold |
|---|---|
| Direction accuracy, material changes (stable truth) | ≥ 90% |
| Large-regression recall (≥ +50%, including new workloads) | ≥ 90%, with ≥ 75% flagged at ≥ +50% ("strict") |
| False-warning rate on immaterial changes | ≤ 20% |
| Magnitude bucket within one bucket | ≥ 80% |
| CI cost | k ≤ ~2 production-run equivalents, and the break-even frequency ≤ the workload's actual run frequency |
| CI latency | ≤ the production runtime of the affected models, plus ~1 min of dbt overhead |

## 2–10. [FILL]

## 11. E6: frequency extrapolation (SIMULATED)

Recurring cost = per-run Δ × future runs. Runs must be forecast from telemetry. For each pattern,
300 synthetic 180-day histories were generated and the next 30 days forecast
(`experiments/frequency.py`):

(table: `results/tables/frequency.md`)

- **Cron schedules** (daily, hourly with rare retries, monthly) are essentially exact (≤1% error).
- **BI traffic with a weekday pattern:** 6–8% error from calendar composition alone. Naive Poisson
  intervals *never* covered the truth (0% coverage). Count noise is not the dominant error;
  calendar and trend structure is. Intervals must model structure, or they are overconfident.
- **Seasonal peaks absent from history** are missed by ~67% (a 3× peak). This is
  **NOT_RELIABLY_PREDICTABLE** from history. It needs customer configuration (known seasons) or
  ≥1 year of history.
- **Sparse ad-hoc jobs** (~4 runs/quarter): median error 100% (p90 200%), so any recurring estimate
  is ±100%.
- **Data-arrival-driven rebuilds** (dbt State–style skipping): ~10% median error, 26% at p90.
