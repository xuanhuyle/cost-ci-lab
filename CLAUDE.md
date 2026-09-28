# Cost CI — technical feasibility investigation

Governing brief: `COST_CI_TECHNICAL_FEASIBILITY_CLAUDE_CODE.md` (read it if context was lost).
Current state and next steps: `STATUS.md` (read first, keep short and current).

## The one question
Can a pre-merge cost-diff engine produce estimates reliable enough to influence merge decisions?
A negative answer is a successful outcome. Do not optimise for a demo.

## Rules that are easy to forget
- Label every material claim: `MEASURED` / `DOCUMENTED` / `INFERRED` / `ASSUMED` / `UNVALIDATED`.
  Local DuckDB results are `MEASURED (local engine)`; they are never proof of Snowflake/Databricks/BigQuery behaviour.
- Platform primitives are classified `DIRECTLY_MEASURED` / `DERIVED` / `ESTIMATED` / `UNAVAILABLE`.
- No LLM in the numeric estimator path. Estimators are deterministic or statistical.
- Scenario definitions (`benchmark/scenarios/*`) must never contain expected estimator outputs; ground truth is measured.
- No SaaS shell (no auth, dashboards, multi-tenancy, polished UI).
- External accounts: no destructive/irreversible actions and no spend without explicit owner approval.
  The gcloud credentials on this machine belong to an unrelated project — do not use them unless the owner approves.
- Record evidence in `docs/EVIDENCE_LOG.md` (IDs `E-###`), unresolved owner asks in `docs/OWNER_REQUEST.md`.
- Commit at meaningful checkpoints.

## Layout
- `costci/` — harness library (change detection, execution/measurement, pools/billing, estimators, metrics).
- `benchmark/project/` — base dbt project (TPC-H based, adapter-portable SQL).
- `benchmark/scenarios/<id>/` — one PR each: `scenario.yaml` + overlay files replacing base files.
- `experiments/` — runnable scripts that produce `results/`.
- `live/` — prepared-but-unvalidated live-platform runbooks and SQL.
- `docs/` — deliverables; `docs/research/` holds raw per-platform research notes.

## Environment
Windows 11, Python 3.11 venv at `.venv` (`.venv/Scripts/python`). 4 cores / 16 GB RAM laptop:
keep production-scale local data modest (TPC-H SF ≤ ~3) and set DuckDB `memory_limit`.
