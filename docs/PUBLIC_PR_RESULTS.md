# Public-PR shadow-production results

Results of `NEXT_EXPERIMENT_PUBLIC_PR_SHADOW_PRODUCTION.md`. Companion documents:
`docs/PUBLIC_CORPUS_SEARCH.md` (Phase 1), `docs/PUBLIC_CORPUS_PROTOCOL.md` (Phase 2,
pre-registration), `docs/SHADOW_PRODUCTION_DESIGN.md` (Phase 4). The prior-stage decision
`docs/DECISION.md` is unchanged and remains the record of the previous stage.

Evidence labels: `MEASURED_PUBLIC_CORPUS` (measured here, on the public corpus, local engine),
`MEASURED_LOCAL` (measured in the previous stage's lab), `DOCUMENTED`, `INFERRED`,
`SHADOW_ASSUMPTION`, `UNVALIDATED`. **No `MEASURED_LIVE` result exists.** No Snowflake, BigQuery
or Databricks execution took place.

---

## 1. Corpus

**Selected: `tuva-health/tuva-core`** — an open-source healthcare data model (claims + clinical →
normalised core layer and marts), maintained by a company and deployed by real healthcare
organisations. Not a tutorial.

| | |
|---|---|
| Unit | first-parent squash-merge commit `C` on `main`; MAIN = `C^`, PR = `C` |
| Frame | all cost-relevant such commits merged 2026-02-04 … 2026-09-08 |
| Frame size | **93** |
| Why that window | 2026-02-04 is the day the repository's own DuckDB CI workflow landed (PR #1193, `dbt_v1.10.15_duckdb_build_full_refresh.yml`). The maintainers ran a **full-refresh DuckDB build on every PR** for the whole window, so engine support is not an assumption |
| Data | published to the public `tuva-public-resources` S3 bucket, pinned per commit by the repository's own `tuva_core_data_asset_version` var and loaded by its own `duckdb__load_seed` macro. Anonymously readable |
| Rewriting | **none**. No PR's SQL was modified to make it run |
| Clone pinned at | `9cf2d1f7` |

Candidate assessment for twelve other repositories, and why each was accepted or rejected, is in
`docs/PUBLIC_CORPUS_SEARCH.md` §2. The corpus feasibility gate **passed on reconstructability**.

### What this corpus cannot support

- No Snowflake/BigQuery/Databricks accuracy claim. The engine is DuckDB.
- No claim about the real recurring dollar cost of any PR to Tuva Health or to anyone running
  Tuva. All monthly dollars here are `SHADOW_ASSUMPTION` and describe the shadow environment only.
- No industry base rate of expensive regressions. One repository, one domain, one seven-month
  window.
- No consumer/BI workload: the public corpus exposes none, and inventing one would be fabrication.
  The consumer-driven failure modes the previous stage found (`s10`/`s11` materialisation sign
  flips, millisecond consumers in `E-030`) are therefore **not** exercised.

---

## 2. Structural comparison with the previous stage's benchmark (`MEASURED_PUBLIC_CORPUS`)

Census of cost-relevant PRs (touching a model `.sql`, a macro `.sql`, or project config). No PR was
inspected for cost.

| Corpus | n | files/PR (median) | 1 model `.sql` | >1 model `.sql` | >=10 model `.sql` | macro | project config |
|---|---|---|---|---|---|---|---|
| **Previous stage's synthetic benchmark** | 26 | **1** | **88%** | **0%** | **0%** | **4%** | **8%** |
| tuva-core (window) | 95 | 7 | 26% | 52% | 31% | 42% | 38% |
| tuva-core (all scanned) | 218 | 4 | 22% | 44% | 23% | 27% | 47% |
| cal-itp/data-infra | 83 | 5 | 31% | 59% | 7% | 19% | 16% |
| OHDSI/dbt-synthea | 38 | 11 | 16% | 71% | 42% | 29% | 45% |
| matsonj/nba-monte-carlo | 58 | 17 | 28% | 64% | 29% | 24% | 40% |
| dcaribou/transfermarkt-datasets | 23 | 7 | 52% | 43% | 9% | 26% | 26% |

**S1.** The previous stage's benchmark is structurally unrepresentative of natural dbt PRs in a
cost-relevant direction: 88% single-model and 0% multi-model, against 43–71% multi-model and
7–42% touching ten or more model files across five independent real repositories.

**S2.** Macro changes are 5–10x more common in natural PRs (19–42%) than in the benchmark (4%), and
project-config changes 2–6x more common (16–47% vs 8%). These are precisely the classes where
`state:modified` was shown incomplete (`E-023`, `E-031`), so the two detector fixes the previous
stage proposed carry more weight on natural PRs, not less.

**Consequence for the previous stage's economics.** `E-037` measured CI analysis cost at a median
of 2.5–4.6 production-run equivalents on a population whose median blast radius is one model.
Counterfactual-execution cost scales with blast radius. Section 5 reports the measured figure on
natural PRs.

---

## 3. Reconstruction (`MEASURED_PUBLIC_CORPUS`)

Processed in merge order from the 93-PR frame until the pre-registered split was full.

| | |
|---|---|
| PRs scanned | **38** |
| Usable | **30** (79%) |
| Excluded | **8** (21%), every one `X4_NO_GRAPH` |
| Split | 10 development (#1175–#1230), 20 holdout (#1233–#1278) |
| Median reconstruction cost | 52 s per PR (2 dbt invocations: parse MAIN, `state:modified+` on PR) |

### R1. 21% of natural cost-relevant PRs are invisible to a counterfactual engine

All 8 exclusions are the same condition: the PR's diff **produces no node in the compiled graph**
under the project's own configuration. They are version bumps (#1198, #1205), documentation-only
changes to model YAML (#1210), and changes to SQL that the configured deployment never builds
because the owning model family is gated off by a project var (#1199 `fhir_preprocessing`, and
#1228, #1247, #1260, #1273).

This is not a harness limitation; it is a property of real repositories. A cost gate built on
counterfactual execution has nothing to say about a fifth of the cost-relevant PR stream, because
there is nothing to execute. Those PRs are not necessarily cost-neutral in a *differently
configured* deployment of the same project — which is precisely why the exclusion is reported
rather than silently treated as "immaterial".

### R2. Blast amplification is 15x at the median

| | median | p90 | max |
|---|---|---|---|
| Models the PR modifies directly (`state:modified`) | **1** | — | 53 |
| Nodes that must be executed (`state:modified+`) | **31** | 50 | 53 |
| Amplification (executed / modified) | **15x** | — | 53x |

The median natural PR changes **one** model and obliges the counterfactual to rebuild **31**. This
is the measured form of the prediction in `docs/PUBLIC_CORPUS_SEARCH.md` §3: the previous stage's
CI-cost figure (`E-037`: 2.5–4.6 production-run equivalents) was measured on a benchmark whose
median blast radius was one model, so it understates the cost of the same method on natural PRs.

### R3. Reconstruction itself is cheap and exact

No PR required a dependency reconstruction approximation: `packages.yml` is pinned in-repo at every
commit, `dbt deps` resolved at every commit attempted, and `dbt parse` succeeded on every MAIN tree
(median 15 s with partial parsing). Zero PRs were excluded for `X1_DEPS`, `X2_PARSE`, `X3_ENGINE`
or `X5_EMPTY_DIFF`. Reconstructing natural PRs from a public repository was the *easy* part of this
experiment.

### R4. The changed-var detector never fired

Not one PR in the 93-PR frame changed a top-level `vars:` default, so the detector added for the
class `state:modified` provably misses (`E-023`, dbt-core#4304) selected nothing. The gap is real
but did not occur in this repository's seven-month window. `MEASURED_PUBLIC_CORPUS`; it says
nothing about how often that class occurs elsewhere.

---

## 4. Transfer: pre-merge CI prediction vs later shadow-production truth

*(filled from `results/public_pr/scores.json`)*

---

## 5. CI analysis cost on natural PRs

*(filled)*

---

## 6. Comparator

*(filled)*

---

## 7. Shadow economics

*(filled)*

---

## 8. Threats to validity

*(filled)*
