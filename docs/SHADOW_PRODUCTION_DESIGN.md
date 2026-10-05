# Shadow-production design (pre-registration)

Phase 4 of `NEXT_EXPERIMENT_PUBLIC_PR_SHADOW_PRODUCTION.md`. Written before any holdout truth is
observed. Companion to `docs/PUBLIC_CORPUS_PROTOCOL.md`.

The previous stage defined "truth" as extra repetitions under almost identical conditions. That is
what this design exists to stop doing.

## 1. What is being separated

| | **Phase A — pre-merge CI** | **Phase B — shadow production** |
|---|---|---|
| When | produced and frozen for a PR before that PR's Phase B | only after that PR's prediction file exists and is hashed |
| Engine threads | **2** | **4** |
| DuckDB `memory_limit` | **3 GB** | **8 GB** |
| Concurrency | isolated, no other query load | **background load**: a second connection replaying a fixed read workload over the core relations for the duration of the measurement |
| Cache warmth | **cold** — a fresh process per variant, no priming | **warm** — a fixed priming scan of the principal input relations before measurement |
| Data snapshot | **T0** (the corpus data assets as published) | **T1 = T0 + deterministic growth** if the development-set check clears it, §3 |
| Database file | a copy of the production database made before the measurement | the production database itself |
| Repetitions | 2 per variant (the CI budget is part of what is being measured) | 2 per variant |

Every one of those is a plausible operational difference, not a pathology. No parameter was chosen
to make the gap large; the direction of each (CI smaller/colder/isolated/older data than production)
is the ordinary direction of the real gap, and it is the direction E3 (`E-039`) showed can distort
and even flip ratios.

## 2. The production context (`SHADOW_ASSUMPTION`)

Fixed before holdout truth, identical for every PR unless the PR itself changes the schedule:

- **Workload:** the project's own scheduled dbt job. For a given PR, the measured workload is the
  affected node set `A` = dbt `state:modified` ∪ rendered-SQL diff, plus all dbt descendants.
  Nodes outside `A` are unchanged by construction, so they cancel in the delta. This is verified on
  the development set, not assumed (§6).
- **Schedule:** the job runs **daily**, i.e. 30 runs per month, every day of the month.
- **Pool:** one dedicated, time-metered warehouse, billed per second of engine time with a 60-second
  minimum per run — the Snowflake dedicated-warehouse rule from `E-011`, replayed by
  `costci.pools`. Price is a unit rate; results are reported as relative cost and as
  shadow-dollars, never as anyone's real bill.
- **No non-dbt consumers.** The public corpus exposes no BI workload, and inventing one would be
  fabrication. **Stated limitation:** the consumer-driven failure modes the previous stage found
  (materialisation sign flips, `s10`/`s11`; millisecond consumer queries, `E-030`) are therefore
  *not* exercised here. This experiment can only confirm or refute transfer for the batch-job class.

**None of this describes Tuva Health's real production environment, or that of anyone running
Tuva.** Schedules, warehouse topology, consumer mix and negotiated pricing are not public. Every
monthly figure produced here is a property of the shadow environment only.

## 3. Deterministic data growth between Phase A and Phase B

Production data is larger and later than the snapshot CI saw. This is modelled by a deterministic,
schema-preserving growth step applied to the **source seed tables** of the synthetic patient data,
after a PR's Phase A prediction is frozen, and only if the development-set check in §6 clears it:

- For each synthetic input table, take the deterministic subset of rows whose primary key hashes
  into the first quartile (`hash(pk) % 4 == 0`), i.e. **+25% volume**.
- Suffix every *internal entity* identifier (`person_id`, `patient_id`, `member_id`, `claim_id`,
  `encounter_id`, `appointment_id`, `location_id`, `practitioner_id`) with a fixed marker, applied
  identically in every table so referential structure is preserved.
- Shift every date/timestamp column by **+180 days**.
- Leave external code columns untouched (`npi`, diagnosis/procedure/LOINC/SNOMED codes), so joins
  to the public reference and terminology tables keep their real selectivity.

No model SQL is touched. The growth is reproducible from a seed and recorded in
`results/public_pr/growth.json`.

Rationale: data growth is the condition under which the previous stage's sampling estimators failed
worst (`E-027`, `s06`; `s22` sign flip at scale). A transfer test that holds data fixed would avoid
the known failure mode.

## 4. Per-PR procedure

For PR `i` in merge order:

**Phase A (CI), run for PR `i` before PR `i`'s Phase B** (see the amendment in
`docs/PUBLIC_CORPUS_PROTOCOL.md` §12 for why the phases interleave per PR rather than
all-A-then-all-B):

1. Check out `C^` and `C` into two reusable worktrees; install packages (cached by dependency-file
   hash + commit).
2. `dbt parse` both; save the `C^` manifest as the deferral state.
3. Detect changes: `state:modified`, its sub-selectors, and the changed-var detector; take the
   union, then `+` for descendants. Record both detectors separately (this re-tests `E-023` and
   `E-031` on natural PRs).
4. Copy the production database to a CI database.
5. In the CI regime, build `A` from the `C^` tree, then from the `C` tree, 2 repetitions each,
   interleaved, each in a fresh process.
6. Freeze the prediction artifact: direction, relative magnitude, bucket, monthly shadow delta,
   confidence grade, analysis seconds, analysis production-run equivalents, evidence used.

**Phase B (shadow production), only after PR `i`'s prediction is written and hashed:**

7. Apply the growth step, if the development-set check cleared it (§3, and the
   amendment in `docs/PUBLIC_CORPUS_PROTOCOL.md` §12).
8. Prime the cache; start the background load.
9. In the production regime, build `A` from the `C^` tree (this is the production baseline for
   those nodes), then deploy — build `A` from the `C` tree — 2 repetitions each.
10. Stop the background load. Record realised per-node times and the realised monthly shadow delta.
11. The production database retains the `C` state, so production advances along `main`'s real
    history, PR by PR, exactly as a real deployment would.
12. **If a PR cannot be measured** (CI or production build failure, or the compute cap), the PR is
    still *deployed* into shadow production without being measured. Otherwise every later PR would
    be evaluated against a base state that never existed on `main`. The deploy-only step is
    recorded per PR.

**Honest limitation of step 9.** The MAIN side of production truth is measured contemporaneously
with the PR side, in the production regime, rather than being read from telemetry recorded days
earlier. What is temporally and environmentally separated is the *prediction* from the *truth*:
different engine size, different concurrency, different cache state, and a wall-clock gap. A fully historical baseline would additionally require a stable
production timeline per node, which a 7-month replay on one laptop cannot provide. This is a
weakening of the design and is reported as such.

**Limits of the "cold" CI arm.** Each CI run is a fresh process, so DuckDB's buffer pool starts
empty, and no priming query is issued. The *operating system's* page cache is not cleared, and
copying the 1.8 GB production database to the CI database immediately beforehand leaves much of it
resident. The CI arm is therefore colder than production at the engine level but not at the OS
level, so the cache-warmth gap between the two regimes is narrower than the design intends. The
other three gaps (engine threads, memory limit, concurrent load) are unaffected.

## 5. Caps and safety

- Per-PR Phase A cap **45 min**, Phase B cap **45 min** (`docs/PUBLIC_CORPUS_PROTOCOL.md` §7).
  Exceeding either is recorded as `ABSTAIN` ("too expensive to measure"), which is an outcome.
- DuckDB `memory_limit` set explicitly in both regimes; `temp_directory` under `work/pub`.
- No external account is touched. All data comes from an anonymous read of a public S3 bucket and
  is mirrored locally after the first fetch.

## 6. Checks run on the development set only

1. **Containment:** do nodes outside `A` change their execution time between `C^` and `C` beyond
   noise? If they do, `A` is the wrong workload definition and the definition is corrected before
   F2 — on development data only.
2. **Noise floor:** repeated-run coefficient of variation per node in each regime, to size the
   intervals and to confirm that the inherited 10% materiality threshold is above the floor.
3. **Comparator threshold `T`** for the high-cost-workload review rule.
4. **Blast-radius cost distribution**, to see how often the 45-minute cap binds.

## 7. Live platform (Phase 5)

Snowflake is **not** executed. No Snowflake account or credential is available, and the gcloud
credentials present on this machine belong to an unrelated project and are not used.

Nothing in this document is presented as a live-platform result. The DuckDB shadow environment
tests *transfer across execution conditions*; it cannot test Snowflake's warehouse behaviour,
`QUERY_ATTRIBUTION_HISTORY`, metering, or multi-cluster scale-out. The exact owner action needed to
run the live phase is in `docs/OWNER_REQUEST.md`.

## 8. Freeze points

Recorded in `results/public_pr/freeze.json` as they happen: F1 (manifest), F2 (estimator/harness
before the first holdout prediction), F3 (holdout predictions before any Phase B run), F4 (truth
evaluation). See `docs/PUBLIC_CORPUS_PROTOCOL.md` §10.
