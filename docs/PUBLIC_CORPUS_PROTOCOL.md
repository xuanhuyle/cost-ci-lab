# Public PR corpus protocol (pre-registration)

Phase 2 of `NEXT_EXPERIMENT_PUBLIC_PR_SHADOW_PRODUCTION.md`.

**This document is written before any cost truth is observed.** Everything in it — the frame, the
sampling rule, the allowed exclusions, the materiality thresholds, the metrics, the comparator and
the decision thresholds — is fixed now. Changes after holdout truth is observed are not permitted;
changes before it must be recorded in §10 with a reason and a timestamp.

Pre-experiment baseline (estimator and harness as inherited): **`0ea6284`**.
Corpus clone pinned at **`tuva-health/tuva-core@9cf2d1f7`** (`main`, 2026-09-08).

## 1. Unit of analysis

One **PR** = one first-parent squash-merge commit `C` on `main` of `tuva-health/tuva-core`.

- **MAIN version** = the tree at `C^`.
- **PR version** = the tree at `C`.

Both are real, previously-shipped states of the project. This avoids branch-environment
reconstruction entirely: there is no approximation step between the public history and what is
executed. `DOCUMENTED` (Tuva squash-merges; verified over 277 first-parent commits).

## 2. Frame (the population)

All first-parent commits on `main` with a merge timestamp in

> **[2026-02-04, 2026-09-08]**

whose diff touches at least one of: a model `.sql`, a macro `.sql`, or project configuration
(`dbt_project.yml`, `packages.yml`, `package-lock.yml`).

**n = 93.** Enumerated mechanically in `public_corpus/census_tuva.json`.

The window **start** is the date Tuva's own DuckDB CI profile landed (PR #1193, 2026-02-04). This is
a repository-capability criterion, fixed before any outcome was seen. The window **end** is the
clone's `main` HEAD. No PR was looked at for cost before the window was chosen.

## 3. Chronological sampling rule

Process the 93 commits **in merge order**, oldest first. For each, attempt reconstruction (§5).

- The **first 10** that pass reconstruction form the **development / calibration set**.
- The **next 20** that pass form the **locked holdout**.
- Everything after that is the **reserve**, used *only* to replace a holdout case invalidated by a
  genuine harness bug, in merge order.

No PR is chosen, skipped, reordered or swapped for any reason other than the allowed exclusions
below.

## 4. Development / holdout separation

Temporal: the development set is strictly older than the holdout set. The holdout's production
truth is not inspected while the harness is being adapted.

If fewer than 20 usable holdout PRs remain after exclusions, the result is reported with the
explicit statement that **statistical confidence is weak**, and recall/false-warning figures are
reported with their exact numerators and denominators.

## 5. Reconstruction criteria and allowed exclusions

A PR is **usable** when, for both `C^` and `C`:

1. `dbt deps` resolves (the pinned package revisions still exist);
2. `dbt parse` succeeds;
3. the change-detection layer produces a node set;
4. that node set executes to completion on DuckDB in at least one variant.

### Allowed exclusions (declared now, before outcomes)

| Code | Exclusion | Rationale |
|---|---|---|
| `X1_DEPS` | `dbt deps` fails at `C^` or `C` | historical dependency no longer resolvable — unrelated to the change |
| `X2_PARSE` | `dbt parse` fails at `C^` or `C` for a reason present on **both** sides | the project was broken at that commit independently of the diff |
| `X3_ENGINE` | the selected node set fails to build at **both** variants because of a DuckDB incompatibility present on `main` | the project did not support the engine at that commit; not a property of the change |
| `X4_NO_GRAPH` | the diff touches only files that produce no node in the compiled graph on this engine *and* the project does not build them (for example a macro only ever dispatched on Snowflake) | nothing is executable; logged separately because the count is itself a finding |
| `X5_EMPTY_DIFF` | the first-parent diff is empty (merge bookkeeping) | nothing changed |

A PR that compiles and runs but turns out to change nothing measurable is **not** excluded. It is an
immaterial case and it counts in the false-warning denominator.

A PR whose measurement exceeds the per-PR compute cap (§7) is **not** excluded either. It is
recorded as an `ABSTAIN` / "too expensive to measure" outcome, which is a result.

### Exclusions that are NOT allowed

"too small", "not interesting", "obviously cheap", "too hard for the estimator", "makes the results
worse", "not representative", "duplicate of another PR", "a revert".

### Exclusion log

`results/public_pr/exclusion_log.json`, one record per excluded PR:
`{pr, sha, merged_at, code, detail, phase, decided_at, outcome_known_at_exclusion: bool}`.
`outcome_known_at_exclusion` must be `false` for every exclusion in the holdout; any `true` entry
invalidates that case and is reported.

## 6. Materiality and direction (inherited, not redefined)

Taken unchanged from `costci/metrics.py` at baseline `0ea6284`:

- `rel = (per-run engine seconds of the affected workload with PR - the same with MAIN) /
  the same with MAIN`. Because the schedule is identical in both arms, this equals the relative
  change in monthly engine seconds. Monthly **dollars** are reported separately, in both the
  marginal and the attributed view, because the warehouse's idle policy decouples dollars from
  resource for a short workload (`E-038`); materiality is defined on resource, exactly as the
  previous stage's truth was (`METRIC = latency_s`).
- **immaterial**: `|rel| < 0.10`; **increase**: `rel >= +0.10`; **decrease**: `rel <= -0.10`
- **large regression**: `rel >= +0.50`
- magnitude buckets: the nine `metrics.BUCKETS` bands.

These thresholds were set in the previous stage, above the lab's measured noise floor, and are
**not** re-opened after holdout results.

## 7. Compute caps

- **Per-PR CI analysis cap:** 45 minutes wall clock on this laptop. Exceeded ⇒ `ABSTAIN`
  ("too expensive to measure"), recorded with the elapsed time.
- **Per-PR shadow-production cap:** 45 minutes wall clock.
- DuckDB `memory_limit` is set explicitly in both regimes (see `docs/SHADOW_PRODUCTION_DESIGN.md`).

## 8. Pre-registered metrics

Computed on the **locked holdout** only. Development-set figures are reported separately and are
never presented as the result.

**Primary (technical)**

1. **Direction accuracy** on material changes.
2. **Material-regression recall** — fraction of truly material increases predicted as increases;
   and **large-regression recall** (`rel >= +0.50`) separately.
3. **False-warning rate** — fraction of truly immaterial PRs flagged as increase or decrease.
4. **Magnitude bucket accuracy** — exact, and within one bucket.
5. **Abstention quality** — direction accuracy among HIGH-confidence cases vs the rest. Abstention
   is informative only if the abstained/low-confidence cases are measurably less reliable.
6. **Ranking quality** — Spearman correlation between predicted and realised monthly delta.
7. **Transfer error** — `median |log(predicted delta / shadow-production delta)|` on material
   changes, plus the sign-flip count. This is the headline number of the experiment.
8. **CI analysis cost** — production-run equivalents (`k`), the same unit as `E-037`.
9. **CI latency** — wall-clock seconds per PR.

**Economic (shadow environment only, `SHADOW_ASSUMPTION`)**

`avoided_shadow_cost / analysis_cost`, with the schedule and capacity policy fixed in
`docs/SHADOW_PRODUCTION_DESIGN.md` before holdout truth. This is not customer ROI and is not
labelled as such anywhere.

## 9. Required comparator

**C1 — high-cost-workload review rule.** Flag a PR for manual review if it touches any workload
whose historical shadow-production baseline cost exceeds a threshold `T`. `T` is chosen on the
**development set only**, by taking the value that maximises development-set F1 against material
regressions; the chosen `T` is then frozen and recorded before holdout evaluation.

**C2 — cheapest existing estimator in the repo that needs no counterfactual execution.** From
`costci/estimators.py` at baseline: the static-plan estimator (`EXPLAIN`-derived output cardinality).

Both comparators are reported at comparable recall to Cost CI. If Cost CI is only marginally better
while materially more expensive, that is recorded as **negative evidence**.

## 10. Leakage controls and freeze points

| Freeze | What is frozen | Recorded where |
|---|---|---|
| F0 | pre-experiment estimator/harness baseline | `0ea6284` (in `STATUS.md`) |
| F1 | corpus manifest (the 93, the split rule, the exclusion rules) | `b02b0dd` / `6768fc8` (`public_corpus/manifest.json`) |
| F2 | estimator + harness, before the first holdout prediction | git SHA recorded in `results/public_pr/freeze.json` |
| F3 | holdout predictions, before any shadow-production run | git SHA + per-PR prediction artifacts under `results/public_pr/holdout_predictions/` |
| F4 | final truth evaluation | git SHA of the commit adding `results/public_pr/holdout_truth/` |

Rules:

- Once F3 exists, the estimator implementation and configuration do not change.
- If a genuine software bug invalidates a holdout case: record the bug, invalidate **that** case,
  fix it, and draw a **replacement from the reserve in merge order**. Never re-run an invalidated
  case after tuning and report it as holdout performance.
- Development-set results may inform harness changes between F1 and F2 only.
- The holdout's shadow-production truth is produced only after F3.

## 11. Threats this protocol does not remove

- One repository, one domain, one engine. Generalization beyond that is not claimed.
- The shadow production environment is constructed by the same agent that runs the estimator. The
  mitigation is that its parameters are fixed in writing before holdout truth, not that the agent is
  independent.
- Materiality is defined on *shadow* monthly cost, which depends on a schedule that Tuva's real
  users do not necessarily run.
- DuckDB run-to-run noise (`E-009`: CV 5–29%) sets a floor on what "material" can mean; the 10%
  threshold sits close to that floor for short statements, so short-statement cases will carry wide
  intervals.

## 12. Amendments

Any change to this document before holdout truth is appended here with date, reason and the git SHA
of the amendment. No amendment after F3 is valid.

All three amendments below were made **before any holdout measurement ran**.

| Date | Change | Reason |
|---|---|---|
| 2026-10-05 | §5 step 3: the **full rendered-SQL diff is replaced by a targeted changed-var detector**. The detector diffs the top-level `vars:` block of `dbt_project.yml` between `C^` and `C`, then selects every model whose `raw_code`, or a macro it depends on, reads one of the changed vars, and adds their descendants. | `dbt compile` of this project does not run against an empty catalog: an `on-run-start`/seed hook queries `_tuva_synthetic.appointment_seed`, so a full rendered diff would need a populated warehouse per commit pair and roughly doubles the per-PR cost. The targeted detector covers exactly the class `state:modified` is *proven* to miss (`E-023`, dbt-core#4304) at negligible cost. It does **not** cover env-var or Jinja-rendering differences, which is recorded as a limitation. |
| 2026-10-05 | Phase A and Phase B are **interleaved per PR** (predict, freeze, then deploy and measure) rather than all predictions first. | The shadow production database has to be in the PR's *base* state when its prediction is made, and production advances along `main` by deploying each PR in turn. Storing a 1.3 GB database snapshot per PR is not affordable. The brief specifies the freeze per PR ("Only after the prediction is frozen"), and the estimator is frozen at F2 before the first holdout PR, so no holdout outcome can influence any prediction. |
| 2026-10-05 | The split is **10 development + 20 holdout** instead of 15 + 25. | That is the brief's own stated target ("~10–15 earliest usable PRs", ">=20 later usable PRs"), and the per-PR measurement cost measured during harness bring-up (8 full dbt invocations over a 1.3 GB database on a 4-core laptop) makes 40 PRs unaffordable in the available time. Choosing 30 before any truth is observed is preferable to running out of time with a partially measured holdout. |
| 2026-10-05 | The deterministic **data-growth step** of `docs/SHADOW_PRODUCTION_DESIGN.md` §3 is made **conditional** on a development-set check that it does not cause build failures, and is reported as not-applied if the check fails. | Appending rows to derived relations can break model assumptions in a third-party project. Risking the whole experiment on an untested perturbation is worse than reporting that one of the six CI/production gap dimensions was not varied. |
