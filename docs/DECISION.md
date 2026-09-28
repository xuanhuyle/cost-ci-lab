# Decision: technical outcome **B, "Useful but narrow"**

> Can we build a pre-merge cost-diff engine whose estimates are reliable enough to influence
> engineering merge decisions?

**Yes, but only as a *measurement-and-replay* system for a narrow class of workloads. It cannot be
built as a cheap *predictor*.**

**What works.** Execute the changed workloads at production scale: on a zero-copy clone, or as a
PR-only run against the workload's own production history. Then replay the capacity pool's billing
over a month.
- In the lab, the full-clone A/B variant got the direction of **every** material change right and
  caught **every** large regression.
- Its magnitude was within ~10% (median), and 96% of its estimates were within one magnitude bucket.
- The PR-only variant costs about half as much: 94% direction, one miss.
- Intervals built from measured run-to-run noise were close to calibrated, and the grades derived
  from them were informative.

**What does not work.** Every cheaper route made wrong-sign or missed-material errors on realistic
PRs:
- static plans;
- dry-run-style byte counts;
- four ways of sampling data;
- scale extrapolation.

Post-hoc calibration did not repair them.

**The consequences:**
- **CI cost.** A reliable check costs ≈2.5–4.6 production runs of the affected workloads per
  analysis. That pays off only for workloads run more than ~40–70 times a month.
- **Dollars.** Dollar translation is only unambiguous on dedicated or per-query-billed compute. On
  shared or prepaid capacity the marginal dollar is a policy-dependent range, and it can even have
  the opposite sign to the attributed dollar.

The functionality is buildable, and the layer that stops it being wrong is real. But most of the
system is dbt plus platform-telemetry integration, and the evidence shows no deep or transferable
technical moat.

**Evidence base, and its limit.**
- **Evidence behind the verdict:**
  - documented platform facts (~300 primary sources, `PLATFORM_FEASIBILITY.md`);
  - a local lab: DuckDB + real dbt on TPC-H, 26 adversarial PRs, 8 supplementary experiments
    (`RESULTS.md`).
- **The limit:** no live Snowflake/Databricks/BigQuery measurement was possible (`OWNER_REQUEST.md`),
  so every platform-specific accuracy statement below is `INFERRED`.

## Why B, and not A, C or D

| Outcome | Verdict | Deciding evidence |
|---|---|---|
| **A: Strong primitive** | No | The only reliable estimator is "run it at production scale". That is conceptually simple and costs production compute, so it is not a reusable predictive core. Cheap estimators fail on meaningful classes (E1: 62–88% direction; wrong-sign on s14/s22). Calibration cannot fix them (E7). Dollar meaning depends on pool policy (E2). |
| **B: Useful but narrow** | **Yes** | For scheduled SQL/dbt workloads on dedicated or per-query-billed compute, with enough run frequency to pay for execution, production-scale estimates were decision-grade in the lab (full clone: 100% direction, 100% large-regression recall, 96% within one bucket, calibrated noise intervals). Outside that region, quality degrades to LOW or NOT_VIABLE (ARCHITECTURE §7). |
| **C: Integration product** | Partly true, not sufficient | Change detection, lineage, telemetry joins, price lists, the PR-comment UX and BigQuery on-demand dry runs are commodity (E-019: `dbt-costgate`, dbt Cost Insights, Infracost). But a product assembled *only* from those gets documented, reproducible cases wrong (see below). |
| **D: Fundamentally unreliable** | No | Within the narrow class, estimates were consistently useful and uncertainty grades were informative. Unpredictability is concentrated in identifiable conditions (see Q4). |

A pure integration product gets these cases wrong:
- materialisation changes, without consumer discovery (s10/s11 sign flips);
- var/config changes, with dbt state only (s24);
- millisecond, high-frequency queries measured once (E-030);
- dollars on absorbed capacity reported as attributed dollars (E2).

## Answers to the ten questions

### 1. Can this be built?
**Yes**, as five pieces:
1. **Change detection:** dbt `state:modified` plus a rendered-SQL diff.
2. **Consumer-aware workload mapping:** dbt lineage plus platform access history.
3. **A measurement policy:**
   - statically skip workloads whose plans are identical;
   - execute the changed workloads PR-only against history, or as an A/B on a zero-copy clone;
   - use noise-adaptive repetition for cheap statements.
4. **A pool-aware monthly replay** with an explicit pricing policy.
5. **Graded intervals.**

All five were built and exercised end-to-end in the lab (`costci/`, `experiments/`). It **cannot** be
built as a model that predicts production cost from code, plans, bytes or samples. On this
benchmark that approach was not decision-grade (E1, E7, E-025…E-027).

### 2. For exactly which workload classes?

| Grade | Workload class | Conditions |
|---|---|---|
| **HIGH** | Scheduled dbt/SQL models (tables, and incremental models with their target cloned) on a **dedicated Snowflake warehouse**; any query under **BigQuery on-demand** (already commodity via dry run) | The workload runs more than ~40–70×/month (so the check pays for itself, E10); production history exists; CI can use a production-scale clone on the production warehouse size (E3). |
| **MEDIUM** | Relations with BI/app consumers; models on warehouses shared across teams; Snowflake Adaptive warehouses (per-query metering, but no published formula); Databricks serverless jobs and SQL warehouses (DBUs appear only after ≤24 h); BigQuery autoscale-only reservations | Usage deltas are measurable. Dollars are a range whose meaning depends on pool state and on a policy (marginal vs attributed), or they are observable only after the CI run. Millisecond consumers need many repetitions. |
| **LOW** | Prepaid or baseline capacity with headroom; multi-cluster scale-out; classic Databricks job clusters (VM cost outside the platform); non-SQL Spark | Marginal $ is 0 until saturation, then a step; or attribution is indirect. |
| **NOT_VIABLE** | Shared all-purpose Databricks clusters; serverless side-costs (auto-clustering, MV/dynamic-table refresh); sparse, seasonal or ad-hoc workloads; infrequent heavy jobs such as monthly runs | No attribution path, vendor estimators at ±50–100%, frequency is unforecastable (E6), or execution costs more than the risk (E10). |

### 3. What level of accuracy or classification quality is realistic?

**In the lab** (`MEASURED`, local engine, 26 PRs):

| Estimator | Direction on material changes | Large-regression recall | False warnings | Within one bucket | Median magnitude error |
|---|---|---|---|---|---|
| Full-clone A/B + history | **100%** | **100%** | 20% (all near the ±10% threshold) | 96% | ~10% |
| PR-only vs history | 94% | 89% | 20% | 96% | ~14% |
| Hybrid (static → samples → clone) | 88% | 100% | 10% | 88% | ~13% |
| Cheap strategies (static plan, bytes, 4 sampling schemes, extrapolation) | 62–88% | 78–100% | 0–60% | 69–85% | ~27% to ~6× |

The full-clone estimator had 0 wrong-sign errors and 0 missed material changes. Each other strategy
had at least one wrong-sign error or missed a material change.

**On a real platform** (`INFERRED`), expect worse. The lab's full clone *is* the production data;
real CI differs in warehouse size, concurrency, cache warmth, data growth and plan learning. When
the lab introduced those gaps deliberately (E3, `MEASURED`):
- a smaller CI engine overstated ratios by up to +136% and **flipped one sign** (s22);
- concurrent production load shifted ratios by −18% to +58%;
- cold, unwarmed single runs understated ratios by up to 29%.

So E1's figures are an upper bound. They hold only if CI runs on the **production warehouse size**
with a warm-up, and the interval is widened for contention. A realistic target is:
- a correct **direction class** and a **magnitude bucket within one** for HIGH-grade cases;
- dollar **ranges**, not points.

The brief's >90% direction and >90% recall bars are plausible *only* for the HIGH class with
production-scale execution. No cheap strategy met them.

### 4. What cannot be predicted reliably before deployment?
- **Frequency changes made outside the repo, and seasonality:**
  - unseen seasonal peaks were missed by 67% (E6);
  - sparse or ad-hoc workloads are ±100% (E6).
- **The sign and size of scale-dependent changes when CI data is smaller than production:**
  - s22 is −27% at production scale but a regression in samples;
  - s06's +1,413% is a +4% "effect" in a 1% sample.
- **Marginal dollars on shared or prepaid capacity**, until a policy is chosen; the policy is not
  learnable from telemetry (E2).
- **Concurrency-driven scale-out steps and production contention**, beyond an interval (E3).
- **Serverless side-costs** (auto-clustering, materialised-view and dynamic-table refresh,
  `OPTIMIZE`), whose vendor estimators are ±50–100% (E-010).
- **Cost of Python/Spark on shared all-purpose clusters.**
- **Negotiated prices on Databricks**, which are invisible (customer configuration).
- **Anything whose cost comes from production conditions that CI does not reproduce:** optimiser
  learning (Snowflake Optima, BigQuery history-based optimisation), cache state, cross-workload
  physical effects.

### 5. Can uncertainty be represented honestly and usefully?
**Yes, for measurement noise.**
- 80% intervals propagated from measured repeated-run variance covered the truth 84% of the time
  (full clone) and 80% (hybrid).
- The derived grade predicted correctness: HIGH was right on direction 100% of the time, MEDIUM 67%
  (E5).

**Honest representation also requires:**
- (a) widening intervals for CI-vs-production condition gaps (E3), frequency (E6) and pool policy
  (E2);
- (b) always stating whether the dollar figure is *marginal* or *attributed*;
- (c) a "not measurable" outcome for classes graded LOW or NOT_VIABLE, rather than a number.

Point estimates should not be shown alone.

### 6. Does a common abstraction survive across Snowflake, Databricks and BigQuery?
**Yes, but not the one proposed.**
- **What survives:** `CostImpact = Σ_pools [Bill_p(month with PR usage) − Bill_p(month with MAIN
  usage)]`, with a per-workload usage delta and a pool billing function. One engine can run it; three
  thin adapters supply measurement, telemetry and billing (`costci/providers.py`, ARCHITECTURE §1–2).
- **What fails:** "cost per query × frequency". The same measured change is +$208/month on a
  Snowflake warehouse and +$1 under BigQuery on-demand (s06). A consumer-driven change is
  +$57 attributed but −$11 marginal on a busy warehouse (s10) (E2, `SIMULATED` under
  `DOCUMENTED` rules).
- **Portability varies.**
  - Snowflake (dedicated) is the cleanest fit.
  - BigQuery on-demand is easy but already commodity.
  - Databricks is the weakest for a synchronous verdict: billing latency up to 24 h, a disk cache
    that cannot be disabled, VM cost outside the platform, and negotiated prices that are invisible.

### 7. What is technically hard versus commodity?

| Commodity (exists or is easy) | Hard, or at least non-trivial (where naive tools go wrong) |
|---|---|
| Parsing the dbt manifest; `state:modified`; lineage | Rendered-SQL change detection (vars/env/config), and consumer discovery beyond dbt |
| Reading query history and billing tables; per-model attribution (≥6 post-hoc tools) | **Safe, representative counterfactual execution:** clone + defer + incremental state + cache control + interleaving + noise-adaptive repetition. Hard operationally, not algorithmically |
| Price lists; BigQuery dry-run × $/TiB (`dbt-costgate`) | **Pool-aware economic translation** (uptime, minimums, idle, autoscale steps, prepaid baseline), plus a stated marginal-vs-attributed policy |
| PR comments and threshold gates (Infracost pattern) | **Uncertainty grading** that includes transfer, frequency and policy terms |
| Zero-copy clone / `dbt clone` | Choosing *what not to run* (static screen), and spend caps for super-linear PRs, where the check costs the most (E10: max k ≈ 36) |

**Answer to "a genuinely difficult and reusable technical core, or integrations plus arithmetic?"**
Mostly integrations plus careful measurement engineering, plus a thin but real modelling layer (pool
replay, consumer-aware mapping, noise and uncertainty).
- The lab found **no** cheap predictive capability that would be hard to replicate and valuable at
  once.
- The calibration signal is per workload and per pool. Transfer across customers is unproven: no data
  exists here to test it, and the mechanisms observed are customer-specific.
- dbt Labs already holds most ingredients: CI jobs, rendered-SQL hashing in "dbt State", and Cost
  Insights history (E-019). That is a platform risk.

### 8. What is the narrowest technically credible V1?

**"Cost regression gate for high-frequency dbt models on Snowflake dedicated warehouses."**

Scope and trigger:
- Only models (and their dbt descendants) that run ≥ ~daily. Hourly and frequent models are the
  sweet spot (E10).
- **Detection:** `state:modified` ∪ rendered-SQL diff.
- **What gets executed:** changed models, their direct children and the consumers of changed
  relations (consumers come from `ACCESS_HISTORY`). Deeper descendants are only screened: plan
  identical and row counts unchanged ⇒ skip (E4).

Measurement:
- A static screen skips workloads with identical plans.
- Changed workloads get **one PR-only run on a zero-copy clone**, with `--defer`, `dbt clone` of
  incremental targets, and `USE_CACHED_RESULT=FALSE`. The run is compared with the workload's
  production history. Use an A/B when history is thin or noisy.
- It runs on a pinned single-cluster CI warehouse **of the same size as production**. A smaller CI
  warehouse distorts ratios and can flip their sign (E3).
- Repeat millisecond statements until stable.

Economics:
- Replay the dedicated warehouse's billing for the job schedule.
- For consumer changes on shared BI warehouses, report the **usage** change plus an *attributed* $
  range. Never report it as marginal.

Output and guardrails:
- The PR comment warns only on **≥ +50% or ≥ $X/month at HIGH grade**, and lists the drivers.
- Everything else is informational.
- A per-PR compute cap applies, with an explicit "too expensive to measure" outcome.

**Excluded:** Databricks, BigQuery editions, Python models, serverless features, sparse or seasonal
jobs, and any claim of predicting cost without running the change.

(BigQuery on-demand can be added cheaply via dry run, but it is not differentiated.)

### 9. What evidence remains missing?
1. **Any live-platform measurement.** Snowflake is the planned target (`live/snowflake/`,
   `OWNER_REQUEST.md` §1). Specifically:
   - Does an X-Small CI run predict the production-warehouse ratio?
   - Is Snowflake's run-to-run noise comparable to the lab's?
   - Does `QUERY_ATTRIBUTION_HISTORY` track execution-time estimates?
   - Does the pool replay reproduce `WAREHOUSE_METERING_HISTORY`?
2. **A real PR corpus.** Base rates of material regressions, their frequency mix, and how many
   changes a static screen could clear. The lab's 26 PRs were hand-written, so they carry no base
   rates.
3. **Real production telemetry**: schedules, consumers, shared-pool load. This determines how much
   spend sits in the HIGH class at all.
4. **Validation of the pool replay against metered bills.**
5. **Tolerance.** Do teams accept ≈2.5–4.6 production runs of CI compute and the added latency per
   PR on hot models?

### 10. What is the next rational step?

**Narrow the concept, then run one more technical experiment before any MVP.** Customer discovery
runs in parallel.

- **Technical (1–2 days, ≤60 Snowflake credits).** Run the prepared live Snowflake experiment. Also
  run a *retrospective* test on one real dbt repository's last ~20–50 merged PRs: would the V1 gate
  have flagged the changes that actually raised the bill?

  Proceed to an MVP only if both hold:
  - HIGH-grade verdicts keep ≥90% direction accuracy on the real platform;
  - the retrospective finds material regressions in high-frequency models often enough to justify
    the per-PR CI spend.
- **Discovery (in parallel).** Test the narrow value proposition, not the broad vision:
  - "Would you pay ~3–5 production runs of compute per PR, on your hottest models, to block large
    cost regressions?"
  - "Do you want marginal or attributed dollars on shared warehouses?"
- **Do not** build the multi-platform product, the "+$5,200/mo across Snowflake + Databricks +
  Anthropic + Datadog" comment, or an ML cost predictor. The evidence does not support them.
- **Stop** if the live run shows Snowflake CI-vs-production transfer errors that push HIGH-grade
  direction accuracy below ~90%. Also stop if real PR histories show material regressions in
  high-frequency models are rare. In either case, what remains is dbt Cost Insights plus alerting,
  which already exists.
