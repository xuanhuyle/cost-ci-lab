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
