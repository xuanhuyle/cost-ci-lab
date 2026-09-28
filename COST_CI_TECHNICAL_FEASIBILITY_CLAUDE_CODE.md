# Cost CI — Technical Feasibility / Falsification Prompt for Claude Code

<role>
You are acting as a senior systems engineer, data-platform engineer, and technical due-diligence lead.

Your job is not to validate my idea or build an attractive demo. Your job is to determine, through research and executable experiments, whether the technical primitive behind the idea is real, useful, and generalisable enough to support a software product.
</role>

<context>
I am investigating a product concept tentatively called **Cost CI**.

Core proposition:

> Before a code change is merged, estimate the incremental recurring infrastructure / data-platform cost that the change is likely to create in production.

The long-term vision is a pull-request control such as:

```text
PR #481 — Estimated recurring cost impact

Snowflake        +$2,300/mo
Databricks         +$800/mo
Anthropic        +$1,900/mo
Datadog            +$200/mo
───────────────────────────
Total            +$5,200/mo
                 +$62,400/yr

Confidence: HIGH

Main driver:
customer_features.sql is expected to consume
~3.2× more compute per production execution.
```

The initial technical scope is narrower:

1. Snowflake
2. Databricks
3. BigQuery
4. dbt / SQL workloads first

LLM APIs, observability vendors, serverless functions, and broader cloud infrastructure are possible later extensions, but they are not part of the first proof unless they materially help test the abstraction.

The product is **not** intended to replace billing or FinOps accounting. The intended value is pre-merge decision support: identifying materially expensive changes before they reach production.
</context>

<objective>
Answer one question:

> **Can we build a pre-merge cost-diff engine whose estimates are reliable enough to influence engineering merge decisions?**

A technically viable result does **not** require accounting-grade precision.

A useful system might be able to say:

- this PR is likely to reduce cost;
- this PR is economically immaterial;
- this PR is likely to increase this workload by roughly 25–50%;
- this PR probably adds $2k–$3k/month;
- this estimate is low-confidence because the workload runs on shared compute.

The investigation must be falsifiable. If the concept is fundamentally too noisy, too slow, too expensive, or too platform-specific, conclude that clearly.
</objective>

<core_hypotheses>
Test these hypotheses rather than assuming them.

### H1 — Change attribution

Given a PR, can we reliably map:

```text
code diff
→ changed model/query/job
→ downstream dependencies
→ production workload(s)
→ historical execution frequency
→ historical resource consumption / spend
```

### H2 — Counterfactual estimation

Can we estimate:

```text
Cost(workload | proposed code)
-
Cost(workload | current production code)
```

before the proposed code is deployed to production?

### H3 — Production extrapolation

Can controlled MAIN-vs-PR measurements, query plans, dry runs, historical telemetry, or a combination of them be translated into a useful estimate of recurring monthly production cost?

### H4 — Calibration

After merge, can actual production telemetry provide ground truth that lets us measure prediction error and improve future estimates?

### H5 — CI practicality

Can the analysis run at acceptable latency and cost for normal CI/CD?

The estimator must not routinely cost more to run than the economic regressions it is designed to detect.

### H6 — Cross-platform abstraction

Is there a real common object called something like:

```text
CostImpact(code_change, production_context)
```

across Snowflake, Databricks and BigQuery?

Or do platform-specific economics make the abstraction misleading?
</core_hypotheses>

<operating_rules>
Follow these rules throughout the investigation.

1. **Investigate before claiming.** Read the relevant code, configuration, schemas, and primary documentation before making factual claims about them.
2. **Prefer primary sources.** Use official Snowflake, Databricks, BigQuery, dbt, GitHub and cloud-provider documentation where possible.
3. **Prefer experiments to speculation.**
4. **Separate evidence levels explicitly.** Label important conclusions as:
   - `MEASURED`
   - `DOCUMENTED`
   - `INFERRED`
   - `ASSUMED`
   - `UNVALIDATED`
5. **Never present simulated results as proof of real-platform feasibility.**
6. **Do not use an LLM to produce the numeric cost estimate.** LLMs may help explain causes later, but the estimator itself should be deterministic or statistically grounded in platform telemetry.
7. **Avoid over-engineering.** Build only what is required to falsify or support the technical hypothesis.
8. **No SaaS shell.** Do not build authentication, billing, dashboards, user management, a polished frontend, or multi-tenancy.
9. **Do not hard-code benchmark answers merely to make tests pass.**
10. **Use git as experimental state.** Make sensible commits/checkpoints as meaningful work is completed.
11. If you create temporary scripts/files while investigating, clean them up unless they are useful reproducible experiment assets.
12. Do not stop early because the task spans multiple context windows. Persist state in the repository and continue.
13. Ask me only for information that genuinely cannot be discovered, inferred safely, or postponed.
14. Do not perform destructive or irreversible actions against any external account without explicit approval.
</operating_rules>

<state_management>
At the start:

1. Inspect the repository completely enough to understand its current state.
2. If the repo is empty, initialise the minimal project structure.
3. Create or update:
   - `CLAUDE.md` — concise persistent instructions for this investigation;
   - `STATUS.md` — current hypothesis status, completed work, next steps, blockers;
   - `docs/EVIDENCE_LOG.md` — important source/experiment evidence with URLs or references.

Keep `STATUS.md` short and current. It exists so the investigation can survive context compaction and multiple sessions.
</state_management>

<phase_1_platform_research>
## Phase 1 — Establish what the platforms actually expose

Research current official capabilities for:

- Snowflake
- Databricks
- BigQuery
- dbt where relevant

For each platform, determine what is available around:

- query/job execution history;
- query plan / execution profile;
- bytes read/scanned/billed;
- compute duration;
- warehouse/cluster/serverless usage;
- actual query/job-level cost attribution;
- billing tables;
- list prices and effective pricing inputs;
- query/job identifiers;
- query tags / labels / metadata;
- execution frequency;
- workload history;
- isolated CI environments;
- cloning / zero-copy cloning / shallow cloning;
- dry runs / explain plans / cost estimation;
- caching;
- shared-compute attribution;
- autoscaling;
- capacity/reservation pricing;
- telemetry latency;
- dbt state/manifest/lineage;
- incremental model behaviour.

For every useful primitive classify it as:

```text
DIRECTLY_MEASURED
DERIVED
ESTIMATED
UNAVAILABLE
```

Do not casually treat runtime, bytes scanned, DBUs, slots, credits, or VM-hours as interchangeable with dollars. Document the conditions under which each can and cannot be converted into economic cost.

Deliver:

`docs/PLATFORM_FEASIBILITY.md`

Include a comparison table and primary-source links.
</phase_1_platform_research>

<phase_2_architecture>
## Phase 2 — Test the abstraction before committing to it

Evaluate whether the following interface is conceptually sound:

```python
class CostProvider:
    def identify_affected_workloads(self, change): ...
    def get_production_baseline(self, workload): ...
    def prepare_candidate_environment(self, change): ...
    def execute_baseline(self, workload): ...
    def execute_candidate(self, workload): ...
    def collect_resource_usage(self, run): ...
    def get_historical_frequency(self, workload): ...
    def get_historical_cost(self, workload): ...
    def estimate_recurring_delta(self, ...): ...
    def validate_realised_cost(self, ...): ...
```

Do not preserve this interface merely because I proposed it.

If the common abstraction should instead be based on workloads, execution units, spend envelopes, or another object, change it.

The architecture should separate:

```text
change detection
workload mapping
benchmark / static estimator
production telemetry
cost normalization
recurring extrapolation
uncertainty/confidence
provider adapter
CI presentation
```

Deliver:

`docs/ARCHITECTURE.md`

The document must answer whether “cost impact of a software change” is genuinely a platform-independent concept.
</phase_2_architecture>

<phase_3_first_experiment>
## Phase 3 — Choose and build the strongest first falsification experiment

Select **one** first platform based on evidence, not preference.

Default to Snowflake + dbt if it offers the cleanest test, but change this choice if Databricks or BigQuery provides a materially stronger experiment.

The experiment must answer:

> Given current code, proposed code, production-like data and historical workload information, can we estimate the recurring economic delta of the proposed change?

Build the smallest executable framework that can test this.

A desirable flow is:

```text
Git diff / dbt state
        ↓
affected workload(s)
        ↓
MAIN baseline
        ↓
PR candidate
        ↓
resource / native cost measurements
        ↓
historical production baseline + frequency
        ↓
estimated recurring delta
        ↓
confidence / evidence
```

A GitHub PR comment renderer is useful only after the estimator itself works. Do not spend time polishing CI UX before validating the primitive.
</phase_3_first_experiment>

<credentials_policy>
If live credentials are available, use them safely.

If live credentials are **not** available:

1. continue with documentation research, architecture, provider interfaces, local reproducible fixtures and all experiments that are genuinely possible;
2. prepare the live experiment so that credentials can be added with minimal work;
3. do not claim real-world prediction accuracy from mocks;
4. create/update `docs/OWNER_REQUEST.md` with the **minimum exact access required** for the next validation step.

Do not repeatedly interrupt me for credentials before exhausting useful work that does not require them.
</credentials_policy>

<phase_4_benchmark_suite>
## Phase 4 — Build an adversarial benchmark suite

Create approximately 15–25 representative changes, including regressions, improvements, and intentionally ambiguous cases.

Candidate scenarios include:

- widen a date filter;
- remove partition pruning;
- expand an incremental window;
- incremental → full refresh;
- many-to-many join;
- increase join cardinality;
- unnecessary `DISTINCT`;
- expensive window functions;
- repeated scans;
- expensive materialisation change;
- table ↔ view changes;
- predicate-pushdown improvement;
- select fewer columns;
- join optimisation;
- increased downstream row count;
- new downstream dependency;
- infrequently executed but expensive workload;
- frequently executed but individually cheap workload.

Also include cases specifically intended to break naive estimators:

- runtime rises while actual marginal dollar cost barely changes;
- bytes scanned rise without proportional spend increase;
- idle/prepaid capacity absorbs a workload increase;
- shared compute makes workload-level attribution ambiguous;
- cache state changes the benchmark;
- candidate increases upstream rows and creates downstream cost later;
- historical frequency is sparse or highly seasonal;
- concurrency changes execution economics.

The suite must be reproducible and must not embed expected estimator outputs into the production logic.
</phase_4_benchmark_suite>

<phase_5_estimators>
## Phase 5 — Compare multiple estimation strategies

Where technically possible, compare:

### A. Static / plan-based
Code diff + metadata + query plan / explain information.

### B. Controlled A/B execution
Run MAIN and PR against equivalent data and execution conditions.

### C. Production-anchored relative estimation
Example:

```text
historical production cost/run = $0.40
candidate / baseline resource ratio = 2.4×
frequency = 1,000 runs/month

predicted candidate cost/run ≈ $0.96
predicted recurring delta ≈ +$560/month
```

### D. Native platform estimator
Use a platform dry-run, billed-bytes estimate, explicit cost primitive, or analogous native capability where available.

### E. Hybrid
Combine historical production telemetry, static analysis and controlled execution.

Do not assume the most sophisticated estimator is best. Compare accuracy, latency, cost, robustness and implementation complexity.
</phase_5_estimators>

<phase_6_metrics>
## Phase 6 — Define and measure viability

The primary objective is decision usefulness, not perfect billing forecasts.

Measure at least:

### Direction accuracy
Did we correctly predict increase / decrease / immaterial?

### Material-regression recall
Did we catch expensive changes?

### False-positive rate
How often would we warn on economically immaterial PRs?

### Magnitude classification
Can we distinguish useful ranges such as:

```text
<10%
10–25%
25–50%
50–100%
>100%
```

### Economic magnitude
Where ground truth permits it, how close is estimated recurring dollar impact?

### Ranking quality
Can we rank PRs by expected economic materiality?

### CI latency
How long does analysis take?

### CI analysis cost
How much does the cost check itself cost?

Use evidence to refine these provisional viability bars:

- >90% correct direction on economically material changes;
- >90% recall for large regressions (for example >50% cost increase);
- acceptably low material false-positive rate;
- useful magnitude bucket for predictable workload classes;
- analysis cheap and fast enough for CI.

If these thresholds are inappropriate, explain and replace them before judging the result.
</phase_6_metrics>

<phase_7_uncertainty>
## Phase 7 — Treat uncertainty as part of the product

Determine whether estimates should be expressed as point estimates, intervals, classifications, or combinations.

Example:

```text
Estimated monthly impact: +$1.8k to +$2.6k
Point estimate: +$2.2k
Confidence: HIGH

Evidence:
- dedicated compute
- representative production-sized data
- 243 historical executions
- stable runtime/resource distribution
```

Versus:

```text
Estimated monthly impact: +$0.5k to +$8k
Confidence: LOW

Evidence:
- shared cluster
- strong concurrency effects
- only 4 historical executions
```

Investigate whether confidence can be quantitatively grounded using observed variance, historical sample size, attribution quality and benchmark stability.

Do not invent confidence labels without evidence.
</phase_7_uncertainty>

<phase_8_failure_modes>
## Phase 8 — Attack the idea

Investigate these failure modes explicitly:

- query/result caches;
- shared warehouses/clusters;
- concurrency;
- autoscaling;
- idle or already-paid-for capacity;
- capacity commitments / reservations;
- negotiated pricing;
- underlying cloud VM/network/storage costs;
- serverless vs provisioned compute;
- data growth;
- schedule/frequency changes;
- downstream recomputation;
- incremental models;
- retries;
- orchestration;
- dynamic SQL;
- Python/Spark workloads;
- materialisation changes;
- workload seasonality;
- sparse workloads;
- cross-workload interactions.

For each major failure mode classify it:

```text
SOLVABLE_DETERMINISTICALLY
SOLVABLE_STATISTICALLY
MANAGEABLE_WITH_UNCERTAINTY
REQUIRES_CUSTOMER_CONFIGURATION
NOT_RELIABLY_PREDICTABLE_PRE_DEPLOYMENT
```

Deliver:

`docs/FAILURE_MODES.md`
</phase_8_failure_modes>

<phase_9_downstream>
## Phase 9 — Test downstream cost propagation

Investigate whether this equation is useful:

```text
Δ Cost(PR)
=
direct changed-workload delta
+
downstream workload deltas
```

For dbt, use manifest/state/lineage information where appropriate.

Test whether downstream propagation is:

- reliable and cheap;
- technically possible but CI-expensive;
- useful only one or a few hops downstream;
- too noisy to support.

Do not assume “all descendants” is the correct execution strategy.
</phase_9_downstream>

<phase_10_calibration>
## Phase 10 — Design the post-merge feedback loop

Design, and implement where data permits:

```text
pre-merge prediction
        ↓
merge/deploy
        ↓
production execution
        ↓
actual telemetry/cost
        ↓
predicted vs realised
        ↓
calibration
```

Determine what can reasonably be calibrated:

- per customer;
- per provider;
- per warehouse/cluster;
- per workload;
- per repository;
- per workload class.

Do not claim a machine-learning moat or cross-customer network effect without evidence that transferable signal exists.
</phase_10_calibration>

<phase_11_ci_economics>
## Phase 11 — Test whether the checker is economical

Investigate the paradox that running a production-like workload merely to price it may itself be too costly or slow.

Model or measure:

```text
analysis cost
──────────────
economic risk detected
```

Evaluate approaches such as:

- selective execution;
- sampling;
- smaller representative datasets;
- native dry runs;
- static query plans;
- historical baselines;
- only running candidate rather than MAIN where a trustworthy baseline exists;
- only benchmarking high-risk or high-spend workloads;
- downstream pruning.

Document expected CI latency and analysis cost for representative cases.
</phase_11_ci_economics>

<phase_12_portability>
## Phase 12 — Validate portability, especially Databricks

Even if the live prototype uses only one provider, perform a concrete architecture-level portability test.

For Databricks separately analyse:

- Databricks SQL;
- serverless jobs;
- dedicated job compute;
- shared all-purpose compute;
- Spark workloads;
- DBUs;
- underlying cloud costs;
- system tables;
- query/job attribution;
- Delta shallow clones;
- Photon;
- autoscaling;
- shared-cluster ambiguity.

For BigQuery analyse at least:

- on-demand billing;
- dry runs;
- bytes billed;
- slot consumption;
- capacity/reservation models;
- shared capacity;
- job metadata.

Classify workload families by likely estimate quality:

```text
HIGH
MEDIUM
LOW
NOT_VIABLE
```

The goal is not feature parity. The goal is to determine whether a common commercial product could plausibly support these platforms.
</phase_12_portability>

<phase_13_defensibility>
## Phase 13 — Separate commodity engineering from a hard technical core

Classify the system's components into:

### Commodity / reproducible plumbing
Potential examples:

- GitHub PR comments;
- reading a dbt manifest;
- querying billing tables;
- fetching public price lists.

### Potentially difficult / product-worthy
Potential examples:

- mapping arbitrary code changes to economic workloads;
- creating representative counterfactual execution safely;
- normalising noisy resource measurements;
- handling shared-capacity economics;
- propagating downstream effects;
- translating per-run changes to recurring spend;
- uncertainty quantification;
- predicted-vs-realised calibration;
- cross-provider normalisation.

Do not assume these are defensible merely because they are complicated.

Explicitly answer:

> Is there a genuinely difficult and reusable technical core here, or is this mostly integrations plus arithmetic?
</phase_13_defensibility>

<deliverables>
The repository should end with these durable artifacts:

```text
README.md
CLAUDE.md
STATUS.md

docs/
  EVIDENCE_LOG.md
  PLATFORM_FEASIBILITY.md
  ARCHITECTURE.md
  EXPERIMENT_DESIGN.md
  RESULTS.md
  FAILURE_MODES.md
  DECISION.md
  OWNER_REQUEST.md
```

Also retain the minimum source code, fixtures, tests and experiment scripts required to reproduce the technical findings.

`docs/RESULTS.md` must clearly separate live measured results from simulated/local results.

`docs/OWNER_REQUEST.md` should contain only unresolved items that require my intervention.
</deliverables>

<decision_framework>
`docs/DECISION.md` is the most important deliverable.

End with one of these technical outcomes:

### A — Strong technical primitive
Useful cost impact can be estimated with adequate reliability across meaningful workload classes, and there is a non-trivial reusable technical core.

### B — Useful but narrow
The method works for specific workload/provider configurations but does not generalise cleanly.

### C — Integration product
The functionality is feasible but mostly consists of platform telemetry, pricing APIs and CI plumbing, with limited technical differentiation.

### D — Fundamentally unreliable
Pre-merge production economics are too dependent on unknowable runtime conditions for the estimates to be consistently decision-useful.

Do not select A because an easy benchmark demo works.

For the final assessment answer:

1. Can this be built?
2. For exactly which workload classes?
3. What level of accuracy or classification quality is realistic?
4. What cannot be predicted reliably before deployment?
5. Can uncertainty be represented honestly and usefully?
6. Does a common abstraction survive across Snowflake, Databricks and BigQuery?
7. What is technically hard versus commodity work?
8. What is the narrowest technically credible V1?
9. What evidence remains missing?
10. What is the next rational step:
    - customer discovery / MVP;
    - another technical experiment;
    - narrow the concept;
    - stop?
</decision_framework>

<execution_protocol>
Proceed autonomously.

Use this sequence:

1. Inspect the repo and environment.
2. Write a concise investigation plan to `STATUS.md`.
3. Research and document current platform primitives using primary sources.
4. Form at least two competing technical hypotheses where uncertainty is material.
5. Select the strongest falsification experiment.
6. Implement the minimum experimental harness.
7. Run every meaningful test the current environment permits.
8. Record failures as evidence rather than working around them to make the idea look successful.
9. Update the architecture based on results.
10. Test portability conceptually and in code where practical.
11. Produce the final decision only after reconciling documentation evidence with experiment results.
12. Before finishing, ensure another engineer could reproduce what was actually tested.

Use subagents only when workstreams are genuinely independent or parallelisable. For tightly coupled coding/debugging tasks, work directly to preserve context.

Do not merely produce a research report if executable testing is possible.
Do not merely produce code if the experiment has not established what the code is intended to prove.
</execution_protocol>

<success_condition>
Success is **not** “a working demo.”

Success is reaching a defensible technical conclusion with enough evidence that I can decide whether this deserves a commercial validation phase.

If the evidence says the product is technically weak, that is a successful investigation.
</success_condition>

Begin now.
