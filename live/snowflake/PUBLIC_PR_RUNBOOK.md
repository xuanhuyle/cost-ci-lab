# Live Snowflake phase on the public PR corpus — runbook

Status: **PREPARED, NOT EXECUTED.** No Snowflake account or credential is available. Everything
here is `UNVALIDATED`. The gcloud credentials on this machine belong to an unrelated project and
are not used.

This replaces `live/snowflake/README.md` for the live phase. That runbook provisions TPC-H for the
previous stage's 26 hand-written scenarios; the open question is now transfer on **natural** PRs,
so the live phase must run the same public corpus the local phase ran.

## Why this is cheap to run

The corpus project, `tuva-health/tuva-core`, already supports Snowflake as a first-class target and
already loads its source data from the **same public S3 bucket** by `COPY INTO ... FROM
s3://tuva-public-resources/...` with no `CREDENTIALS` clause (`macros/cross_database_utils/
load_seed.sql`, `snowflake__load_seed`). So:

- **No SQL is ported.** The exact commit pairs replay unchanged.
- **No data is uploaded.** Snowflake reads the public bucket directly.
- The only new code needed is a Snowflake profile and the per-PR driver already written for
  DuckDB (`experiments/public_pr/measure.py`), with `write_profile` swapped for a Snowflake one.

That is a materially smaller lift than the Snowflake work the previous stage had outstanding
(`live/snowflake/README.md` step 5), because dbt itself executes the models here rather than the
harness re-implementing materialisation.

## What the live phase tests that the local phase cannot

| Question | Measurement | Signal |
|---|---|---|
| Does an X-Small CI run predict the production-warehouse ratio on **natural** PRs? | CI on `COSTCI_CI_WH` (XSMALL), shadow production on `COSTCI_PROD_WH` (SMALL) | Direction accuracy and transfer error, against the DuckDB figures |
| Is Snowflake's run-to-run noise comparable to DuckDB's? | 2–4 interleaved reps per variant | CV of `execution_time` vs the local figure |
| Does execution time track Snowflake's own attribution? | `execution_time` vs `QUERY_ATTRIBUTION_HISTORY.CREDITS_ATTRIBUTED_COMPUTE` (≤8 h later) | Rank correlation and ratio stability |
| Does the pool replay reproduce the metered bill? | `costci/pools.py` replay vs `WAREHOUSE_METERING_HISTORY.credits_used_compute` | Error on metered credits per hour |
| Micro-partition pruning | `partitions_scanned / partitions_total` per query | Whether the DuckDB zone-map analogue holds |

## Exact steps

```bash
# 0. owner action (docs/OWNER_REQUEST.md §1): account + COSTCI_ROLE + key-pair auth
export SNOWFLAKE_ACCOUNT=...            # e.g. abcd-ef12345
export SNOWFLAKE_USER=COSTCI
export SNOWFLAKE_ROLE=COSTCI_ROLE
export SNOWFLAKE_PRIVATE_KEY_PATH=/path/to/rsa_key.p8

# 1. provision (a few credits), with the spend cap
snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" --private-key-path "$SNOWFLAKE_PRIVATE_KEY_PATH" \
        -f live/snowflake/public_pr_setup.sql

# 2. adapter
.venv/Scripts/pip install -r live/requirements-live.txt     # dbt-snowflake

# 3. build the shadow-production baseline at the corpus window-start commit,
#    on the production warehouse
COSTCI_TARGET=snowflake .venv/Scripts/python experiments/public_pr/build_baseline.py

# 4. walk the corpus: Phase A on the CI warehouse, Phase B on the production warehouse
COSTCI_TARGET=snowflake .venv/Scripts/python experiments/public_pr/measure.py

# 5. wait >= 8 h for QUERY_ATTRIBUTION_HISTORY, then collect telemetry
snowsql ... -f live/snowflake/telemetry.sql -o output_format=csv > results/live_public_pr/telemetry.csv

# 6. score, then tear down (destructive: export results first)
.venv/Scripts/python experiments/public_pr/score.py
snowsql ... -f live/snowflake/teardown.sql
```

## The one code change still required

`experiments/public_pr/measure.py` and `build_baseline.py` call
`costci.public_pr.write_profile`, which emits a DuckDB profile. A Snowflake variant is ~25 lines:

```yaml
default:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: "{{ env_var('SNOWFLAKE_ACCOUNT') }}"
      user: "{{ env_var('SNOWFLAKE_USER') }}"
      role: "{{ env_var('SNOWFLAKE_ROLE') }}"
      private_key_path: "{{ env_var('SNOWFLAKE_PRIVATE_KEY_PATH') }}"
      database: COSTCI_TUVA
      warehouse: "{{ env_var('COSTCI_WAREHOUSE') }}"   # COSTCI_CI_WH or COSTCI_PROD_WH
      schema: public
      threads: 4
      query_tag: "costci:public_pr"
```

plus `ALTER SESSION SET USE_CACHED_RESULT = FALSE` as a `on-run-start` equivalent (dbt-snowflake
exposes `session_parameters`). It is deliberately **not written and not merged**, because it cannot
be executed or tested without an account, and untested live code in the repository would be
indistinguishable from validated code.

## Budget (INFERRED, not measured)

The local baseline build of the whole project at production data volume took on the order of an
hour on 4 laptop cores. On a SMALL warehouse (2 credits/hour) a full build is plausibly 10–30
minutes; per-PR measurement touches only the affected subgraph. For 30 PRs with 2 repetitions in
each of two regimes:

- baseline build: ~1 credit
- per PR: ~0.3–1.5 credits
- total: roughly **15–50 credits**

The 60-credit resource monitor in `public_pr_setup.sql` is the hard cap; raise or lower
`CREDIT_QUOTA` to the approved budget before running anything.

## Stop line

Nothing above has been executed. The experiment stops here until the owner provides access
(`docs/OWNER_REQUEST.md` §1).
