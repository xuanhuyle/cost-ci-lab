# Public PR corpus search

Phase 1 of `NEXT_EXPERIMENT_PUBLIC_PR_SHADOW_PRODUCTION.md`. Written **before** any cost truth was
observed, and before any harness change. Date: 2026-10-05. Pre-experiment baseline commit `0ea6284`.

The question this document answers is the gate question, not an implementation question:

> Does a sufficiently credible natural public PR corpus exist to make the shadow-production
> experiment worth running?

## 1. Method

Three search channels, all reproducible:

1. **GitHub topic/keyword repository search** (`gh search repos`) over `dbt`, `dbt analytics
   warehouse`, `dbt duckdb project`, `analytics engineering dbt models`, `dbt bigquery public data`
   — 60 + 4x25 results inspected.
2. **GitHub code search** (`search/code` API) for `"type: duckdb" filename:profiles.yml`
   (4,400 hits; first 50 distinct repositories inspected) — the only mechanical way to find dbt
   projects whose *execution environment* is reproducible on a laptop.
3. **Direct inspection of known real operating analytics repositories**: GitLab's
   `gitlab-data/analytics`, Mozilla's `bigquery-etl`, Cal-ITP, the Fivetran / Snowplow / Elementary /
   Brooklyn-Data package families, and dbt Labs' own repositories.

For each surviving candidate a **census** was computed, not a sample:

- `experiments/public_pr/probe.py` — repository metadata, tree contents, merged-PR count.
- `experiments/public_pr/prscan.py` — per-PR changed-file classification via the GitHub API.
- `experiments/public_pr/census_git.py` — the authoritative chronological census, built from the
  **first-parent history of `main`** in a local clone. The API scan is ordered by `updated_at`,
  which is not a valid chronological frame; the git census replaced it for the selected corpus.

**No PR was inspected for whether it "looks expensive" at any point in this phase.** Selection is by
changed-file class and date only.

### Definition used throughout

A commit is **cost-relevant** if its diff touches at least one of: a model `.sql` file, a macro
`.sql` file, or project configuration (`dbt_project.yml`, `packages.yml`, `package-lock.yml`).
This is deliberately broader than "likely to change cost" — narrowing it would be selection on the
outcome.

## 2. Candidates and verdicts

| Repository | Stack | Merged PRs | Cost-relevant | Date range | Commits reconstructable | Data reproducible | Verdict |
|---|---|---|---|---|---|---|---|
| [tuva-health/tuva-core](https://github.com/tuva-health/tuva-core) | dbt; Snowflake / BigQuery / Databricks / Redshift / Fabric / SQL Server / **DuckDB** | 714 | 184 of 277 first-parent commits since 2025-06; **93 since the DuckDB profile landed 2026-02-04** | 2021-11 → 2026-09 | **Yes** — squash-merge onto `main`, so `C^` and `C` are exact buildable trees | **Yes** — all source data is published to a public S3 bucket (`tuva-public-resources`), versioned, and loaded by an in-repo `duckdb__load_seed` macro | **CORPUS A (selected)** |
| [OHDSI/dbt-synthea](https://github.com/OHDSI/dbt-synthea) | dbt + **DuckDB** / Postgres / Snowflake | 54 | 38 | 2024-02 → 2026-05 | Yes | Yes (public Synthea generator output) | Corpus A **backup**; too few PRs for a 15/20 split once exclusions are applied |
| [cal-itp/data-infra](https://github.com/cal-itp/data-infra) | dbt + BigQuery | 2,643 | 83 of last 300 | 2022-10 → 2026-10 | Yes | **No** — sources are ingested GTFS feeds in a private GCP project; no public mirror of the warehouse tables | **Corpus B** (structure only) |
| [matsonj/nba-monte-carlo](https://github.com/matsonj/nba-monte-carlo) | dbt + **DuckDB** | 133 | 58 | 2022-10 → 2026-09 | Yes | Yes (public NBA data) | Rejected: a demonstration project ("Modern Data Stack in a Box") — criterion 7 |
| [dcaribou/transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets) | dbt + **DuckDB** | 138 | **23** | 2021-01 → 2026-08 | Yes | Partly (raw data behind DVC; published copy on Kaggle) | Rejected: fails the >=30 criterion |
| [catalyst-cooperative/pudl](https://github.com/catalyst-cooperative/pudl) | dbt + DuckDB | 2,383 | — | 2017 → 2026 | Yes | Yes | Rejected: the dbt layer is 6 models and is almost entirely data tests |
| fivetran/dbt_shopify, dbt_hubspot, dbt_netsuite | dbt packages | 99–111 each | high | 2020 → 2026 | Yes | Yes (in-repo integration-test seeds) | Rejected: seeds are tens-to-hundreds of rows. Statements run sub-millisecond, so measured cost differences would be pure noise (`E-009`, `E-030`) |
| snowplow/dbt-snowplow-unified, dbt-snowplow-web | dbt packages | 82 / 111 | high | 2021 → 2026 | Yes | Partly | Rejected: no DuckDB target (0 code-search hits) and no live warehouse is available |
| brooklyn-data/dbt_artifacts; elementary-data/dbt-data-reliability; dbt-labs/dbt-project-evaluator | dbt packages | 229 / 806 / 264 | high | 2021 → 2026 | Yes | Yes | Rejected: the modelled data is *dbt's own metadata* — a few thousand rows. No cost signal |
| dbt-labs/jaffle-shop, jaffle_shop_duckdb | dbt | 53 / few | low | 2023 → 2026 | Yes | Yes | Rejected: tutorial projects — criterion 7 |
| gitlab-data/analytics | dbt + Snowflake | historically thousands of MRs | — | 2018 → ? | **No** — gitlab.com returns HTTP 302 for the project page and the API reports `404 Project Not Found` (checked 2026-10-05) | No | Rejected: no longer publicly accessible |
| mozilla/bigquery-etl | Jinja-templated SQL on BigQuery (not dbt) | 8,224 | — | 2019 → 2026 | Yes | No (Mozilla telemetry source tables are private) | **Corpus B** candidate only; not executed |
| Datavault-UK/automate-dv | dbt macro package | 63 | — | 2019 → 2026 | Yes | n/a | Rejected: 0 model `.sql` files; it is a macro library |

### Why tuva-core wins

1. **It is a real operating project, not a tutorial.** The Tuva Project is an open-source healthcare
   data model (claims + clinical → a normalised core layer and marts), maintained by a company and
   deployed by real healthcare organisations. 353 model files, 86 seed contracts, 9 pinned package
   dependencies, and a multi-warehouse CI matrix.
2. **Exact commit pairs come free.** Tuva squash-merges onto `main`. For a merge commit `C`, the
   tree at `C^` *is* the pre-PR production code and `C` *is* the post-PR production code. There is
   no branch-environment reconstruction and no merge approximation. Verified locally:
   `git log --first-parent main` gives 277 commits since 2025-06-01, and 181 of the 188 since
   2025-10-01 carry a `(#NNNN)` PR reference.
3. **The data is genuinely reproducible and genuinely public.** Source data is not in the repo; it
   is published to the `tuva-public-resources` S3 bucket, pinned by a `tuva_core_data_asset_version`
   variable, and loaded by the repository's own `duckdb__load_seed` macro via `read_csv('s3://...')`.
   The bucket is anonymously listable and readable (verified 2026-10-05). The same macro accepts a
   `tuva_seed_duckdb_storage_root` variable, so the corpus can be pinned to a **local mirror** and
   replayed offline and deterministically.
4. **The data is not trivially small.** Terminology assets alone are ~220 MB compressed
   (`terminology__snomed_ct_transitive_closures.csv.gz` is 131 MB), and the built DuckDB database
   exceeds 1.3 GB. Unlike the package candidates, joins against this data take real time.
5. **DuckDB is a first-class, maintainer-validated target.** The README states Tuva Core 1.0 is
   "validated against both dbt Core 2.0 and dbt Fusion on DuckDB", and `integration_tests/README.md`
   documents the exact local DuckDB run command. This matters because the lab's existing engine is
   DuckDB: no PR's SQL is rewritten to make it run.
6. **Enough PRs.** 93 cost-relevant first-parent commits between 2026-02-04 (when the DuckDB CI
   profile landed) and 2026-09-08.

### Verified executability (`MEASURED_PUBLIC_CORPUS`)

Performed on this laptop with the existing lab toolchain (dbt-core 1.12.5, dbt-duckdb 1.11.0,
DuckDB 1.5.5), *before* the gate decision:

| Check | Result |
|---|---|
| `dbt deps` at `HEAD` (9 packages, 8 of them pinned git revisions) | OK |
| `dbt parse` at `HEAD` (668 nodes) | OK, ~80 s |
| `dbt seed --select synthetic_data` from the public bucket | OK, 15 seeds loaded over anonymous S3 |
| `dbt deps` + `dbt parse` at a historical commit (`46c5b24c`, 2026-02-15, PR #1210) | OK, warnings only |
| Full `dbt build` at `HEAD` with `synthetic_data_size: large` | see `docs/PUBLIC_PR_RESULTS.md` |

One environment fix was required and is recorded: Windows `MAX_PATH`. `git config --global
core.longpaths true` is necessary, because the nested package layout
(`integration_tests/dbt_packages/quality_measures/models/.../quality_measures__int_cqm438_*.sql`)
exceeds 260 characters. The machine's registry already had `LongPathsEnabled=1`.

## 3. Structural census of natural PRs (`MEASURED_PUBLIC_CORPUS`)

This is the brief's optional structural-analysis deliverable. It is reported here, before any
measurement, because it is already decision-relevant: it says whether the existing 26-scenario
benchmark is realistic in **shape**. It says nothing about the base rate of cost incidents.

Percentages are of cost-relevant PRs.

| Corpus | n | files/PR (median) | 1 model `.sql` | >1 model `.sql` | >=10 model `.sql` | touches a macro | touches project config |
|---|---|---|---|---|---|---|---|
| **Existing synthetic benchmark** (`benchmark/scenarios/`) | 26 | **1** | **88%** | **0%** | **0%** | **4%** | **8%** |
| tuva-core (all scanned) | 218 | 4 | 22% | 44% | 23% | 27% | 47% |
| tuva-core (2026-02-04 →) | 95 | 7 | 26% | 52% | 31% | 42% | 38% |
| cal-itp/data-infra | 83 | 5 | 31% | 59% | 7% | 19% | 16% |
| OHDSI/dbt-synthea | 38 | 11 | 16% | 71% | 42% | 29% | 45% |
| matsonj/nba-monte-carlo | 58 | 17 | 28% | 64% | 29% | 24% | 40% |
| dcaribou/transfermarkt-datasets | 23 | 7 | 52% | 43% | 9% | 26% | 26% |

**Finding S1 (`MEASURED_PUBLIC_CORPUS`).** The existing benchmark is structurally unrepresentative
of natural dbt PRs, in a specific and cost-relevant direction: it is 88% single-model and 0%
multi-model, whereas natural cost-relevant PRs in five independent real repositories are 43–71%
multi-model, and 7–42% touch ten or more model files. Median files per PR is 1 in the benchmark and
4–17 in the natural corpora.

**Why this matters before any accuracy number is produced.** The repo's CI-cost result (`E-037`:
median 2.5–4.6 production-run equivalents per analysis) was measured on a population whose median
blast radius is one model. Counterfactual-execution cost scales with blast radius. The natural-PR
distribution therefore predicts a materially worse CI-cost figure than the one the previous decision
rested on, independently of accuracy. This is recorded as a prior; it is measured, not assumed, in
the execution phase.

**Finding S2 (`MEASURED_PUBLIC_CORPUS`).** Macro changes are 5–10x more common in natural PRs
(19–42%) than in the benchmark (4%), and project-config changes 2–6x more common (16–47% vs 8%).
Both are exactly the classes where `state:modified` was shown to be incomplete (`E-023`, `E-031`).
The two detector fixes the previous stage proposed are therefore more load-bearing on natural PRs
than the benchmark suggested, not less.

## 4. Corpus feasibility gate

> Can we identify at least ~30 natural historical PRs that are sufficiently reconstructable to
> support a fair experiment?

**Gate verdict: PASS on reconstructability.**

Evidence:

- 93 cost-relevant natural merged PRs exist in a single repository inside a window where the
  project's own maintainers run DuckDB CI (`MEASURED_PUBLIC_CORPUS`).
- Base/head commit pairs are exact, not reconstructed (`MEASURED_PUBLIC_CORPUS`).
- Source data is public, versioned, anonymously readable, mirrorable locally, and loaded by the
  repository's own code with no SQL rewriting (`MEASURED_PUBLIC_CORPUS`).
- Historical dependency sets are pinned in-repo per commit (`packages.yml` with git revisions), so
  the dependency environment is reconstructable per PR (`MEASURED_PUBLIC_CORPUS`).
- `deps` + `parse` verified at both `HEAD` and a February-2026 commit (`MEASURED_PUBLIC_CORPUS`).

The gate passes on *reconstructability*. It does **not** assert that 30 PRs will survive execution.
The exclusion rate is unknown until the reconstruction phase runs, and is itself a reportable
result.

## 5. The two conditions that could still make this uninformative

Both are measured, not assumed, and both are reported whatever they show:

1. **Execution exclusion rate.** If more than roughly half of the 93 PRs fail to build at `C^` or
   `C` for reasons unrelated to the change, the usable corpus drops below the 15 (development) +
   20 (holdout) split and statistical confidence is weak.
2. **Material-change base rate.** If almost no natural PR in the corpus produces a materially
   different cost, recall cannot be estimated, and the honest verdict is `UNINFORMATIVE`, not
   success. The previous stage never measured this quantity, because its PRs were authored to be
   material.

Neither condition may be repaired by adding hand-written scenarios.

## 6. What this corpus cannot support

Stated now, before results, so that it cannot be quietly relaxed later:

- It cannot establish **Snowflake, BigQuery or Databricks** accuracy. DuckDB is the engine.
- It cannot establish the **real recurring dollar cost** of any PR to Tuva Health or to anyone
  running Tuva. Schedules, warehouse topology, consumer mix and negotiated pricing are not public.
  Every dollar figure produced in this experiment describes the **shadow environment only**, and is
  labelled `SHADOW_ASSUMPTION`.
- It cannot establish the **base rate of expensive regressions in industry**. One repository, one
  domain, one seven-month window.
- Corpus B repositories (cal-itp, mozilla/bigquery-etl) are used for **structure only**. No
  prediction-accuracy or cost-incidence claim may be drawn from them.

## 7. Reproduce

```
.venv/Scripts/python experiments/public_pr/probe.py <owner/repo> ...
.venv/Scripts/python experiments/public_pr/prscan.py <owner/repo> <limit> <model_dir_prefix>
.venv/Scripts/python experiments/public_pr/census_git.py work/corpus/tuva-core 2025-06-01 "models/" \
    public_corpus/census_tuva.json
.venv/Scripts/python experiments/public_pr/structure.py
```

Raw outputs: `public_corpus/raw/prs_*.json`, `public_corpus/census_tuva.json`, `public_corpus/structure.json`,
`public_corpus/synthetic_structure.json`.
