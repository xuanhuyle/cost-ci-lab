# STATUS: Cost CI feasibility investigation

Last updated: 2026-09-28 14:22 (session 1)

## Outcome
**B, "Useful but narrow"** (`docs/DECISION.md`). A measurement-and-replay system works for
scheduled dbt/SQL workloads on dedicated or per-query-billed compute run more than ~40–70×/month.
No cheap predictor was decision-grade. Dollars on shared or prepaid capacity depend on policy.
All execution evidence is local (DuckDB + real dbt).

## Hypothesis status (final unless live validation contradicts it)
| ID | Verdict |
|----|---------|
| H1 | Supported, with two fixes: a rendered-SQL diff, and consumer discovery via access history |
| H2 | Supported only by production-scale execution (full-clone A/B: 100% direction, 0 wrong-sign) |
| H3 | Partly: cron plus dedicated pools yes; seasonal/sparse, shared/prepaid pools and condition gaps no |
| H4 | Designed; removes small bias from accurate estimators only; no cross-customer claim |
| H5 | Narrow: k ≈ 2.5–4.6 production runs; break-even at ~40–70 runs/month |
| H6 | Survives as usage delta × pool replay; cost-per-query fails |

## Done
- Research (4 streams, ~300 sources); lab (26 PRs); experiments E1–E10; all deliverables in `docs/`.
- Bugs found in my own tooling and fixed: dbt compile defer (E-003), dateadd pruning (E-008),
  consumer noise protocol (E-030), billing-simulator float residue (E-032).

## Open
- E4 downstream strategies finishing (`results/downstream.json`) → RESULTS §10.
- Live validation: `docs/OWNER_REQUEST.md` (Snowflake trial; optional BigQuery probe; a real PR corpus).

## Blockers
- No live platform access. The gcloud credentials on this machine belong to an unrelated project and
  are not used.

---

## Next experiment: public PR shadow production

Added 2026-10-05 (session 2). Governing brief:
`NEXT_EXPERIMENT_PUBLIC_PR_SHADOW_PRODUCTION.md`. Nothing above this line is revised; the
session-1 results and `docs/DECISION.md` stand as the prior-stage record.

### The kernel now being tested
> A pre-merge counterfactual run can correctly identify material cost regressions from **natural**
> dbt/SQL PRs under **later, meaningfully different** production conditions, with an analysis cost
> low enough to be decision-useful.

### Why the prior local lab is insufficient
1. **The PRs were written by the same agent that evaluated them.** 26 hand-designed adversarial
   scenarios carry no base rate and no evidence of structural realism.
2. **"Truth" came from extra repetitions under near-identical conditions.** E1's 100% direction
   figure is a same-condition upper bound; E3 (`E-039`) showed condition changes alone shift ratios
   −18%…+136% and flipped one sign. Transfer to a later, different production regime is untested.
3. **No live platform measurement exists.** Every executable result is `MEASURED (local engine)`.

An independent audit placed the project at **Evidence Level 0.5–1**, not 3: mechanism partial,
generalization untested, real-world validity untested, economics untested.

### Authorization for this stage
- **No new product work.** No SaaS, dashboard, GitHub App, multi-tenancy, Databricks, new adapters.
- **No new synthetic scenarios** as primary evidence.
- **The estimator is not to be modified** before the public-corpus feasibility gate is decided, and
  is frozen before any holdout truth is observed.
- Pre-experiment baseline (estimator + harness as inherited): **`0ea6284`**
  (`0ea6284c1dba8796338f276157ab6d8aa8085803`).

### First gate
> Can at least ~30 natural historical merged PRs be found in public repositories that are
> reconstructable (exact base/head commits, compilable, data reproducible) well enough to support a
> fair pre-merge-vs-shadow-production experiment?

If NO: the coding work stops, the reason is documented, and no replacement corpus is manufactured.
Search and gate verdict: `docs/PUBLIC_CORPUS_SEARCH.md`.

### Kill condition (project level)
> Stop the pre-merge Cost CI thesis if a representative set of natural PRs cannot be evaluated with
> >=90% material-regression recall and >=90% direction accuracy under later production-like
> conditions, at an analysis cost materially below the regressions it would prevent.

Not to be rescued by more synthetic scenarios, a platform switch, an LLM, more calibration,
post-hoc narrowing, or redefining "material" after seeing holdout failures.
