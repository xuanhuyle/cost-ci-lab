# Live Snowflake falsification run: runbook

Status: **prepared, not executed** (no credentials; see `docs/OWNER_REQUEST.md` §1). All SQL and code
here is `UNVALIDATED`.

## What it tests that the lab cannot

| Question | Measurement | Pass/fail signal |
|---|---|---|
| Does an X-Small CI run predict the production-warehouse ratio? | Same 25 scenarios: CI on `COSTCI_CI_WH` (XS) vs "production" on `COSTCI_PROD_WH` (S) at TPC-H SF10 | Direction accuracy on material changes and large-regression recall ≥ the lab's; ratio error by scenario class |
| Do key-consistent samples transfer on Snowflake? | Runs on `RAW_KEY10` vs `RAW` | Same metrics as the lab's `ab_key10` / `ab_two_point` |
| How noisy are repeated runs? | 8 interleaved reps per scenario | CV of `execution_time` vs the lab's 5–29% (E-009) |
| Is execution time a faithful proxy for Snowflake's own attribution? | `execution_time` vs `QUERY_ATTRIBUTION_HISTORY.CREDITS_ATTRIBUTED_COMPUTE` (8 h later) | Rank correlation and ratio stability across scenarios |
| Does the pool-replay model reproduce the bill? | Replay `WAREHOUSE_EVENTS_HISTORY` / query timeline through `costci/pools.py` vs `WAREHOUSE_METERING_HISTORY.credits_used_compute` | Error on metered credits per hour |
| Pruning behaviour | `partitions_scanned/total` for s01, s02, s13 | Confirms or rejects the "cast defeats pruning" analog (E-005/E-008) |

## Steps

1. The owner provisions access per `docs/OWNER_REQUEST.md` §1 and exports the `SNOWFLAKE_*` env vars.
2. `pip install -r live/requirements-live.txt`, then copy `profiles.yml.example` to `profiles.yml`.
3. Run `setup.sql` (≈ a few credits; resource monitor `COSTCI_CAP` caps total spend).
4. Build the prod schemas: `dbt build --target prod --vars '{source_schema: RAW}'`, and again with
   `schema: PROD_KEY10` / `source_schema: RAW_KEY10`.
5. Run the benchmark with the Snowflake session. **Remaining code work, not done because it can't be
   tested without an account:**
   - `costci/dbtops.py` currently stages compile placeholders in a local DuckDB catalog. For
     Snowflake, dbt-snowflake must compile against the account, with placeholder tables created in
     `CI_MAIN`/`CI_PR`. That is ~50 lines: an adapter-specific `_stage_placeholders`. DuckDB-compiled
     SQL cannot simply be reused because the `dateadd`/interval syntax differs.
   - `costci.measure.measure_env` must take a session factory so it can use
     `live.snowflake.adapter.SnowflakeSession`.

   Use CI reps on `COSTCI_CI_WH` and truth reps on `COSTCI_PROD_WH`.
6. Wait ≥ 8 h, then run `telemetry.sql` queries 3–5 and store the CSVs under `results/live/`.
7. Re-run `experiments/analyze.py` with `results/live/bench` and compare with the lab.
8. Run `teardown.sql`. Destructive: run it only after exporting results.

## Budget arithmetic (INFERRED)

The lab's heaviest scenario runs ~10 s of SF2 work per statement. SF10 is 5× more data; on a Small
warehouse, expect roughly 20–60 s per heavy statement. The whole benchmark is:
- per rep: 25 scenarios × ~2–6 statements × 2 variants;
- 8 reps on S, plus ~7 reps on XS/key10.

That comes to roughly 6–12 warehouse-hours: about 12–24 credits on Small and 3–6 on X-Small. Add
CTAS setup and slack, and **20–40 credits** is expected. The 60-credit cap leaves margin.
