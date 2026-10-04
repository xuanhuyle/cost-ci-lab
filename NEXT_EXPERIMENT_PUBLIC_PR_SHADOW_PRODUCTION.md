# Cost CI — Next Experiment: Public PRs + Shadow Production

<role>
You are acting as a skeptical technical founder, research engineer, and experimentalist.

Your job is **not** to improve Cost CI by default.

Your job is to test the single most important unresolved proposition left by the current repository:

> **Can a pre-merge counterfactual measurement predict the material production-cost effect of a natural, real code change well enough to justify continuing this project?**

A negative result is a successful experiment if it resolves the uncertainty.
</role>

<context>
This repository already contains a substantial technical feasibility investigation. Do **not** treat it as a blank-slate build.

Before doing any new work, read at minimum:

1. `README.md`
2. `STATUS.md`
3. `CLAUDE.md`
4. `docs/DECISION.md`
5. `docs/RESULTS.md`
6. `docs/EXPERIMENT_DESIGN.md`
7. `docs/EVIDENCE_LOG.md`
8. `docs/OWNER_REQUEST.md`
9. `docs/ARCHITECTURE.md`
10. the relevant code under `costci/`, `experiments/`, `benchmark/`, and `live/`

Also inspect the git history, especially the sequence around:

- initial lab scaffolding;
- E1 benchmark;
- the consumer-measurement protocol fix;
- E2–E10;
- the final decision;
- the prepared but unexecuted Snowflake live experiment.

The current repo's own verdict is **B — "Useful but narrow."**

However, the latest independent audit of this project reached a more conservative conclusion:

> The repo has demonstrated that production-scale counterfactual execution can measure SQL/dbt cost differences in a controlled local environment. It has **not** yet demonstrated the commercially interesting mechanism: that a pre-merge measurement transfers reliably to a later, different production environment on natural code changes, at positive economics.

The audit placed the project around **Evidence Level 0.5–1**, not Level 3:

- mechanism: partial;
- end-to-end autonomy: partial;
- generalization: not tested;
- real-world validity: not tested;
- expert usefulness: not tested;
- economic value: not tested.

The audit's main criticism was process-related:

> After E1 showed that cheap prediction was unreliable and E3 showed that execution-condition differences could shift ratios materially and even flip sign, the decision-critical frontier became real-world transfer. Further local calibration, synthetic frequency modelling, provider abstraction, and presentation work added much less evidence than a live transfer test would have.

Do not repeat that mistake.
</context>

<what_is_already_known>
Treat these as the current evidence base, not as hypotheses to re-prove with another synthetic benchmark.

### MEASURED in the existing local lab

- 26 hand-designed dbt PR scenarios were run on DuckDB + real dbt.
- Full production-scale MAIN-vs-PR A/B measurement performed far better than cheap predictors.
- Static plans, byte proxies, data samples, and scale extrapolation all produced wrong-sign or material-miss failures on some cases.
- Full-clone A/B achieved 100% direction accuracy on locally material changes in that lab.
- PR-only-vs-history was cheaper but slightly less reliable.
- Non-dbt consumers were necessary to get some materialisation changes right.
- dbt `state:modified` missed at least one var/config-driven change that rendered-SQL comparison caught.
- Same-change cost meaning depends on billing/capacity regime.
- Reliable analysis cost was approximately 2.5–4.6 production-run equivalents at the median.
- E3 found that changing execution conditions can materially distort ratios:
  - smaller compute overstated some ratios by up to ~136%;
  - one scenario changed sign;
  - concurrency shifted ratios by roughly -18% to +58%;
  - cold single runs understated some effects.

### DOCUMENTED / INFERRED

- Snowflake dedicated warehouses are the cleanest candidate for a live counterfactual measurement experiment.
- BigQuery on-demand has a much easier pre-execution path via dry-run bytes and is therefore a useful control, but a weaker differentiated product wedge.
- Databricks is harder for a synchronous cost verdict because of attribution/pricing/cache complications.
- The repo already contains `live/snowflake/` and `live/bigquery/` preparation.

### NOT demonstrated

- Any Snowflake/Databricks/BigQuery accuracy result.
- Transfer from pre-merge CI conditions to later production conditions.
- Performance on natural historical PRs.
- Real base rate of expensive regressions.
- Positive economics on real PR histories.
- Buyer willingness to pay.
- The claim that AI-assisted coding increases the incidence of expensive changes.
- A defensible multi-platform "financial compiler for code changes."
</what_is_already_known>

<kernel>
The project should now be judged against this single kernel:

> **A pre-merge counterfactual run can correctly identify material cost regressions from natural dbt/SQL PRs under later, meaningfully different production conditions, with an analysis cost low enough to be decision-useful.**

If this mechanism survives, the project deserves another stage.

If it does not, the current pre-merge Cost CI thesis should stop or fundamentally change direction.
</kernel>

<constraint>
The owner does **not** have access to a private production dbt/Snowflake repository, private warehouse telemetry, or historical company billing data.

The owner can use **public repositories and public PR histories**.

Do not treat the absence of private production access as permission to return to hand-written scenarios.

Instead, construct the strongest possible substitute:

> **natural public PRs + reproducible data + a controlled shadow-production environment**

The purpose is to replace both:
1. hand-written code changes; and
2. same-experiment "production truth"

with a stronger temporally separated test.

If live Snowflake credentials are not available, complete every step that does not require them and stop at the exact live-execution boundary with a minimal owner request.

Do not use unrelated credentials already present on the machine.
</constraint>

<non_goals>
Do **not**:

- build a SaaS product;
- build a dashboard;
- build a GitHub App;
- add multi-tenancy;
- add Databricks support;
- add Anthropic/OpenAI/Datadog cost adapters;
- invent more adversarial PR scenarios as the main evidence;
- improve the local estimator unless the new experiment exposes a specific blocking defect;
- tune the estimator on holdout outcomes;
- conduct broad startup-market research;
- claim commercial validation from public-repo results;
- claim that a public shadow environment reproduces a real company's production economics.

The next work must reduce the **transfer/generalization uncertainty**, not polish the product.
</non_goals>

<phase_0_reconstruct_and_freeze>
## Phase 0 — Reconstruct the current state before touching code

Read the repo and write a concise addendum to:

`STATUS.md`

Do not rewrite prior results.

Add a new section named:

`## Next experiment: public PR shadow production`

It should state:

- the kernel above;
- why the prior local lab is insufficient;
- that no new product work is authorized;
- that the first gate is finding a credible natural PR corpus;
- the kill condition defined below.

Before any new estimator changes, record the current estimator / harness commit SHA. This is the **pre-experiment baseline**.

Do not alter historical result files.
</phase_0_reconstruct_and_freeze>

<phase_1_public_corpus_search>
## Phase 1 — Find a credible public PR corpus before building anything

Search public GitHub repositories, and public GitLab repositories if useful, for real dbt / SQL transformation projects with historical PRs or merge requests.

Prefer real operating projects over tutorials.

### Minimum candidate criteria

A candidate repository should satisfy as many of the following as possible:

1. It contains a genuine dbt project or equivalent SQL transformation project.
2. It has a meaningful history of merged PRs/MRs touching:
   - models;
   - macros;
   - materialisations;
   - project config;
   - tests or sources when they affect compiled SQL.
3. At least ~30 consecutive usable merged PRs can be reconstructed.
4. The base/head commit pair is publicly available.
5. Historical dependency versions can be reconstructed well enough to compile.
6. Source schemas/data can be:
   - reproduced from public datasets;
   - recreated from repository fixtures/seeds;
   - mapped to a documented public sample;
   - or generated deterministically from a public schema without changing the logical purpose of the changed queries.
7. The project is not mainly educational examples or toy SQL.
8. The PRs are not selected because they "look expensive."

### Strong preference

Prefer a corpus where the actual data environment is itself reproducible.

Examples of acceptable sources:

- dbt projects built on public Snowflake sample data;
- public analytics projects with seeds/fixtures;
- public projects using BigQuery public datasets;
- open data-stack projects with documented reproducible demo datasets;
- real-company analytics repos where the changed SQL can be executed against a schema-compatible public/synthetic dataset without rewriting the PR logic.

### Important distinction

Create two classes if necessary:

#### Corpus A — executable natural PRs
Real historical PRs that can be executed against reproducible data.

These can enter the quantitative shadow-production experiment.

#### Corpus B — natural but non-executable PRs
Real historical PRs whose private source data cannot be reconstructed.

These may be used only for **structural/generalization analysis**, for example:
- what files real PRs change;
- how often macros/configs/materialisations change;
- how large their blast radius is;
- what fraction the current change detector can parse.

They must **not** be used to claim prediction accuracy or cost incidence.

### Search discipline

Do not cherry-pick PRs that fit the existing benchmark.

For each candidate repo record:

- repo URL;
- dbt/platform stack;
- number of merged PRs;
- number touching cost-relevant transformation code;
- date range;
- whether commits are reconstructable;
- whether data is reproducible;
- likely dependency/runtime burden;
- likely exclusion rate;
- why it is or is not a valid quantitative corpus.

Deliver:

`docs/PUBLIC_CORPUS_SEARCH.md`

### Corpus feasibility gate

Before implementing a new replay harness, answer:

> **Can we identify at least ~30 natural historical PRs that are sufficiently reconstructable to support a fair experiment?**

If **NO**:
- stop the coding work;
- document exactly why;
- propose the least-bad non-coding next step;
- do not manufacture a replacement corpus.

If **YES**:
- select the best corpus using predeclared criteria;
- continue.
</phase_1_public_corpus_search>

<phase_2_sampling_protocol>
## Phase 2 — Pre-register the sample before observing cost truth

The corpus must be selected without looking at which PRs are expensive.

Use a chronological rule, not subjective selection.

Example:

> Take the first N consecutive merged PRs after date D that touch executable dbt/SQL transformation logic and pass the predeclared reconstruction criteria.

Define allowed exclusions **before** measuring performance.

Allowed exclusion examples:
- cannot reconstruct dependency environment;
- missing base/head commit;
- PR does not compile for reasons unrelated to the changed code;
- private upstream schema cannot be reproduced without materially rewriting the PR;
- non-SQL change with no effect on compiled transformations.

Not allowed:
- "too small";
- "not interesting";
- "obviously cheap";
- "too hard for our estimator";
- "makes the results worse."

Maintain an exclusion log with:
- PR;
- exclusion reason;
- decision timestamp/phase;
- whether the outcome was known at exclusion time.

### Development / holdout split

Use a temporal split.

Target, if the corpus allows:

- ~10–15 earliest usable PRs = **development/calibration set**;
- >=20 later usable PRs = **locked holdout**.

Do not inspect holdout production truth while adapting the harness.

If fewer than 20 usable holdout PRs remain, state that statistical confidence is weak.

Deliver:

`docs/PUBLIC_CORPUS_PROTOCOL.md`
</phase_2_sampling_protocol>

<phase_3_reconstruction>
## Phase 3 — Reconstruct the PRs with minimal transformation

For every executable PR:

1. checkout the exact base commit;
2. checkout the exact PR head/merge commit;
3. reconstruct the historical dbt/project dependencies where practical;
4. compile both versions;
5. record:
   - changed files;
   - dbt `state:modified`;
   - rendered-SQL differences;
   - materialisation/config changes;
   - DAG descendants;
   - compile failures;
   - any source-schema substitutions required.

Do not "port" a PR by rewriting its core SQL to fit the experiment.

If source adaptation changes the mechanism of the PR, exclude it and log why.

Build only the minimum reusable adapter necessary to feed these PR pairs into the existing Cost CI harness.

Prefer extending existing modules over creating a second architecture.

Deliver a machine-readable manifest such as:

`public_corpus/manifest.json`

with, for each PR:

- repository;
- PR/MR number;
- base SHA;
- head SHA;
- merge date;
- touched models/macros/config;
- executable yes/no;
- exclusion reason if any;
- dataset mapping;
- dependency/version info;
- split = development or holdout.
</phase_3_reconstruction>

<phase_4_shadow_production_design>
## Phase 4 — Design a temporally separated shadow-production test

The current local benchmark defined "truth" using additional repetitions under almost identical conditions.

Do not do that again.

For each holdout PR, create two distinct phases:

### Phase A — PRE-MERGE prediction

Using only information available before deployment:

- base code;
- PR code;
- historical shadow-production baseline;
- current reproducible data snapshot;
- current schedule/production context;
- current Cost CI estimator.

Produce and freeze:

- predicted direction;
- predicted relative magnitude bucket;
- predicted resource delta;
- dollar estimate only if the billing model supports a defensible dollar translation;
- confidence/abstain decision;
- analysis compute cost;
- evidence used.

Write this to an immutable prediction artifact.

### Phase B — SHADOW-PRODUCTION truth

Only after the prediction is frozen:

1. deploy the PR version into the shadow-production environment;
2. run the relevant workload under a meaningfully different production regime;
3. gather later execution telemetry;
4. compute realised impact;
5. compare against the frozen prediction.

The production phase must differ enough from CI that this is a real transfer test.

Where possible vary at least some of:

- warehouse/compute size;
- concurrent background load;
- cache warmth;
- time between CI and production;
- data snapshot / controlled data growth;
- workload schedule.

Do not deliberately make production pathological. The gap should represent plausible operational difference.

### No holdout leakage

Once the first holdout prediction is generated:

- freeze the estimator implementation and configuration;
- record the git SHA;
- do not modify it based on holdout results.

If a genuine software bug invalidates the experiment:
- record the bug;
- invalidate affected holdout cases;
- fix it;
- use **new unseen PRs** for replacement cases.

Do not rerun the same holdout after tuning and report the tuned result as holdout performance.
</phase_4_shadow_production_design>

<phase_5_live_platform>
## Phase 5 — Use a real warehouse if available

### Preferred decision platform: Snowflake

The strongest test is Snowflake because the current thesis narrowed toward:

> high-frequency dbt/SQL workloads on dedicated Snowflake warehouses.

Reuse `live/snowflake/` where useful, but do not blindly execute the old synthetic scenario plan.

Adapt the live harness to the public-PR corpus.

The live test should measure at minimum:

- query execution time;
- bytes scanned;
- warehouse size;
- query tags;
- repeated-run noise;
- later query history;
- query-attributed compute where available;
- warehouse metering where available;
- CI analysis credits;
- production-phase credits.

Use a dedicated experiment database/schema and explicit query tags.

Use a strict resource monitor / spend cap.

Do not use any unrelated account or credential.

### If no Snowflake account exists

Do not fake this phase in DuckDB and call it live validation.

Instead:

1. finish corpus discovery, protocol, reconstruction, and executable harness;
2. produce the exact Snowflake setup/run command;
3. update `docs/OWNER_REQUEST.md` with the minimum owner action needed;
4. stop before paid/live execution.

### BigQuery

BigQuery on-demand may be used as a **control** if public data makes execution materially easier.

Because dry-run bytes already solve much of pre-execution pricing there, BigQuery success must not be used as evidence that the differentiated Snowflake thesis works.

### Databricks

Do not add Databricks in this experiment.
</phase_5_live_platform>

<production_context>
## Production context in a public-repo experiment

A public repo will usually not reveal the original company's true:

- schedule;
- BI consumer mix;
- warehouse topology;
- negotiated pricing;
- idle capacity;
- production traffic.

Therefore distinguish two separate questions.

### Question 1 — Per-run transfer
Can pre-merge measurement predict the later per-run resource impact of the PR?

This **can** be tested in shadow production.

### Question 2 — Real recurring monthly dollars
Did this PR cost the original company $X/month?

This generally **cannot** be inferred from a public repo.

Do not pretend otherwise.

For the shadow environment, define a deterministic schedule and capacity policy that is:
- fixed before holdout outcomes;
- identical across PRs unless the PR itself changes scheduling;
- explicitly labelled `SHADOW_ASSUMPTION`.

Monthly-dollar outputs describe the shadow environment only.

Do not use them as claims about the originating public repository/company.
</production_context>

<comparator>
## Required comparator

Cost CI must beat a cheap credible baseline.

At minimum implement:

> **High-cost-workload review rule:** if a PR touches a workload whose historical shadow-production baseline cost is above threshold T, flag it for manual review; otherwise do not flag it.

Choose T on the development set only.

Also compare against the cheapest existing estimator already in the repo that requires no full counterfactual execution.

The purpose is to answer:

> Does the expensive counterfactual machinery materially outperform a much simpler review policy?
</comparator>

<metrics>
## Metrics

Pre-register before holdout truth.

### Primary technical metrics

For material holdout changes:

1. **Direction accuracy**
2. **Material-regression recall**
3. **False-warning rate**
4. **Magnitude bucket accuracy**
5. **Abstention quality**
   - are low-confidence cases actually less reliable?
6. **Ranking quality**
7. **Transfer error**
   - pre-merge estimate vs later shadow-production truth
8. **CI analysis cost**
9. **CI latency**

### Economic metric in the shadow environment

Compute:

`avoided_shadow_cost / analysis_cost`

under explicit assumptions.

Do not claim this is customer ROI.

### Comparator metric

Report Cost CI and the trivial high-cost-workload review rule at comparable recall.

If Cost CI is only marginally better while materially more expensive, that is negative evidence.
</metrics>

<success_failure>
## Pre-registered decision thresholds

Use these as the default unless the development set reveals they are incoherent. If you change them, change them **before holdout truth is observed** and explain why.

### Success

Continue the technical thesis only if, on the locked holdout:

- >= 90% recall on materially expensive regressions;
- >= 90% correct direction on material changes;
- <= 20% false warnings on immaterial changes;
- confidence/abstention is informative rather than cosmetic;
- Cost CI materially outperforms the trivial high-cost-workload rule at similar recall;
- analysis cost is less than ~25–33% of avoidable shadow-production cost across the tested corpus;
- no systematic class of natural PRs causes repeated wrong-sign errors.

### Failure

Treat the current pre-merge thesis as failed if any of the following holds robustly:

- production-condition transfer pushes direction accuracy below ~90%;
- material-regression recall is below ~90%;
- false warnings are operationally noisy;
- the accurate method requires essentially reproducing full production so expensively that expected savings disappear;
- a trivial expensive-model review rule performs nearly as well at much lower cost;
- too many natural PRs cannot be reconstructed or mapped without project-specific manual work;
- the method regularly abstains on the very PRs that matter.

### Uninformative

The experiment is uninformative if:

- the public corpus cannot be executed without materially rewriting the changed logic;
- there are too few material changes in the holdout to estimate recall;
- live platform access is unavailable;
- the shadow environment is too similar to CI to test transfer.

Do not convert an uninformative result into a positive result.
</success_failure>

<kill_condition>
The project-level kill condition is:

> **Stop the pre-merge Cost CI thesis if a representative set of natural PRs cannot be evaluated with >=90% material-regression recall and >=90% direction accuracy under later production-like conditions at an analysis cost materially below the regressions it would prevent.**

This must be treated as a real kill condition.

Do not rescue the project by:
- adding more synthetic scenarios;
- changing the target platform;
- adding an LLM;
- adding more calibration;
- narrowing to a trivial case after the fact;
- redefining "material" after seeing holdout failures.
</kill_condition>

<structural_analysis>
## Optional secondary analysis: natural PR structure

Only after Corpus A is selected, and without delaying the core experiment, you may use a larger Corpus B of natural but non-executable PRs to compare the current synthetic benchmark with reality.

Questions:

- How large are real dbt PRs?
- How often do they touch:
  - one model;
  - multiple models;
  - macros;
  - vars/config;
  - materialisations;
  - incremental logic?
- How often does rendered-SQL blast radius exceed changed-file blast radius?
- How often would the existing 26 synthetic scenarios look structurally representative vs exotic?

This analysis can tell us whether the old benchmark is realistic in **shape**.

It cannot tell us the base rate of real cost incidents.

Do not use it to claim economic pain frequency.
</structural_analysis>

<deliverables>
Create only the artifacts needed for this experiment.

At minimum:

`docs/PUBLIC_CORPUS_SEARCH.md`
- candidate repos;
- search methodology;
- selection rationale;
- corpus feasibility gate.

`docs/PUBLIC_CORPUS_PROTOCOL.md`
- inclusion/exclusion rules;
- chronological sampling rule;
- development/holdout split;
- preregistered metrics and thresholds;
- leakage controls.

`public_corpus/manifest.json`
- machine-readable PR corpus.

`docs/SHADOW_PRODUCTION_DESIGN.md`
- exact CI vs production separation;
- frozen prediction protocol;
- platform setup;
- resource caps.

`results/public_pr/`
- development results;
- locked holdout predictions;
- shadow-production truth;
- final comparison;
- exclusion log.

`docs/PUBLIC_PR_RESULTS.md`
- result narrative;
- evidence labels;
- comparator;
- threats to validity.

`docs/NEXT_DECISION.md`
- one final decision:
  - CONTINUE
  - PIVOT
  - STOP
  - BLOCKED / UNINFORMATIVE

Update:
- `STATUS.md`
- `docs/EVIDENCE_LOG.md`
- `docs/OWNER_REQUEST.md` only where the experiment reveals a genuinely necessary owner action.

Do not overwrite the historical `docs/DECISION.md`; preserve it as the prior-stage decision.
</deliverables>

<evidence_labels>
Use these labels consistently:

- `MEASURED_LOCAL`
- `MEASURED_LIVE`
- `MEASURED_PUBLIC_CORPUS`
- `DOCUMENTED`
- `INFERRED`
- `SHADOW_ASSUMPTION`
- `UNVALIDATED`

Never turn `SHADOW_ASSUMPTION` into a statement about the source company's real production environment.
</evidence_labels>

<researcher_independence>
The current project has a researcher-adaptation risk because the same agent:

- designed the synthetic benchmark;
- observed failures;
- changed the protocol;
- reran evaluation.

This next experiment must reduce that risk.

Therefore:

1. corpus selection criteria are fixed before cost truth;
2. holdout PRs are fixed before truth;
3. estimator code is frozen before holdout truth;
4. predictions are written before production runs;
5. exclusions are logged before outcomes when possible;
6. post-hoc fixes invalidate affected holdout cases;
7. replacement cases must be previously unseen PRs.

Record exact git SHAs for:
- corpus manifest freeze;
- estimator freeze;
- holdout prediction freeze;
- final truth evaluation.
</researcher_independence>

<working_style>
Work autonomously, but do not confuse autonomy with permission to expand scope.

If the next uncertainty is not a coding problem, do not code.

If public corpus discovery fails, stop and say so.

If live credentials are missing, do everything useful up to the boundary, then request only the minimum owner action.

Prefer:
- real PRs over invented scenarios;
- exact historical commits over reconstructed approximations;
- fixed preregistered rules over judgement after results;
- negative findings over rationalisation;
- one decisive experiment over a roadmap.

Do not help Cost CI survive.

Help determine whether it deserves to.
</working_style>

<first_actions>
Execute in this order:

1. Read the current repo and git history.
2. Update `STATUS.md` with the new kernel and kill condition.
3. Do **not** change estimator code yet.
4. Search for public candidate corpora.
5. Write `docs/PUBLIC_CORPUS_SEARCH.md`.
6. Decide the corpus feasibility gate.
7. If the gate fails, stop.
8. If the gate passes, freeze the corpus protocol and manifest.
9. Reconstruct the development set.
10. Only then make the minimum harness changes required.
11. Freeze estimator/harness before holdout truth.
12. Run the live shadow-production phase only if an approved account exists.
13. Produce `docs/NEXT_DECISION.md`.

The first decision is therefore not:

> "How do we implement public PR replay?"

It is:

> **"Does a sufficiently credible public PR corpus exist to make this experiment worth running?"**
</first_actions>

<final_output>
At the end, report only what the evidence supports.

Use this structure in `docs/NEXT_DECISION.md`:

# Next-stage decision

## Corpus
What was found and how representative it is.

## What was actually tested
Separate public-corpus reconstruction, local execution, and live shadow-production execution.

## What survived
Maximum 5 bullets.

## What failed
Maximum 5 bullets.

## Transfer result
Did pre-merge estimates survive later production-like conditions?

## Comparator
Did Cost CI materially beat the trivial high-cost-workload review rule?

## Economics
Shadow-environment analysis cost vs avoidable cost, with assumptions.

## Remaining untested claims
Maximum 5 bullets.

## Kill condition status
NOT CROSSED / CROSSED / UNINFORMATIVE.

## Decision
CONTINUE / PIVOT / STOP / BLOCKED.

## One-sentence rationale
Exactly one sentence.
</final_output>

Begin now.
