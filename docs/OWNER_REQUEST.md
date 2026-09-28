# Owner request: unresolved items that need you

Everything else in the investigation was done without these. They are listed in order of how much
they would change the conclusion. Nothing here is urgent. The decision in `DECISION.md` stands on
the evidence gathered so far, and each item says what it would validate or overturn.

## 1. Snowflake access for the live falsification run (highest value)

**Why:** every executable result so far comes from a local engine (DuckDB). The decisive open
questions are Snowflake-specific:
- Does a CI run on an X-Small warehouse predict the production-warehouse cost ratio?
- How noisy are repeated runs?
- Does `QUERY_ATTRIBUTION_HISTORY` agree with execution-time measurement?
- Does our warehouse replay model reproduce `WAREHOUSE_METERING_HISTORY`?

**Minimum access** (either option):
- **Option A (preferred): a new Snowflake trial account** that you create. It gives 30 days and
  $400 of credit with no card. I cannot create accounts. Choose **Enterprise** edition, AWS, any
  region (Enterprise is needed for `ACCESS_HISTORY`).
- **Option B:** a sandbox database in an existing account where spend is acceptable.

**Exact grants for a dedicated role `COSTCI_ROLE`:**
- `CREATE WAREHOUSE` and `CREATE DATABASE` on the account. Alternatively, pre-create the objects in
  `live/snowflake/setup.sql` yourself and grant `OWNERSHIP` on them.
- `IMPORTED PRIVILEGES` on `SNOWFLAKE_SAMPLE_DATA`. It is present by default in trials.
- `GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER TO ROLE COSTCI_ROLE;`
- `GRANT DATABASE ROLE SNOWFLAKE.GOVERNANCE_VIEWER TO ROLE COSTCI_ROLE;`

**Authentication:** a user with **key-pair auth**. Put the private key path, account, user and role
in environment variables `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PRIVATE_KEY_PATH` and
`SNOWFLAKE_ROLE`. No passwords.

**Spend cap:** `live/snowflake/setup.sql` creates a resource monitor. I suggest **60 credits**
(≈ $120–$240 depending on edition). My estimate for the planned run is 20–40 credits, dominated by
repeated SF10 runs on Small.

**What I'd run:** see `live/snowflake/README.md`. It runs the same 25 scenarios at TPC-H SF10
("production") vs an SF10 key-consistent 10% sample and an X-Small CI warehouse. It then compares
execution-time estimates with `QUERY_ATTRIBUTION_HISTORY` and warehouse metering.

## 2. Permission decision on BigQuery (cheap control experiment)

**Why:** BigQuery on-demand is the one regime where a native pre-execution estimate (dry run)
exists. A small live probe would measure:
- dry-run bytes vs billed bytes;
- slot-ms run-to-run variance on a real cloud engine;
- `INFORMATION_SCHEMA.JOBS` latency.

This work would make **no resource changes** (no datasets or tables). It would run only public-data
queries with `maximum_bytes_billed` set, and stay under 100 GB processed in total, which is within
the 1 TiB/month free tier.

**The issue:** this machine's gcloud is authenticated as a service account for an unrelated project
(`contractual-harness`), plus your personal account. I have **not** used either.

**Please say which of these you prefer:**
- (a) Use project `<id>` with account `<which>` under the cap above.
- (b) Do not use GCP.

The probe is ready: `live/bigquery/probe.py`. It refuses to run without `--project` and
`--approved`, dry-runs every query first, skips anything above `--max-gb`, and sets
`maximum_bytes_billed` on every job. It takes about 10 minutes.

## 3. Real production telemetry (the test the lab cannot do)

**Why:** H1 (attribution), H3 (frequency and history anchoring) and H4 (calibration) ultimately need
a real dbt project with real query history. The lab's production context is synthetic by
construction.

**Minimum:**
- Read-only access to one real dbt project's `manifest.json` from production runs.
- 30–90 days of query history for its warehouse(s), with one of:
  - Snowflake: `QUERY_HISTORY` + `ACCESS_HISTORY` + `WAREHOUSE_METERING_HISTORY`;
  - BigQuery: `JOBS`;
  - Databricks: `system.query.history` + `system.billing.usage`.
- An export (CSV/Parquet) is enough; no live access is needed.
- Ideally, ~20 merged PRs whose post-merge cost change can be measured. That enables a
  retrospective "would Cost CI have predicted this?" test.

## Not requested

- No credentials were needed for the research, the local lab, or the documents.
- The following MCP connectors in this session showed as unauthenticated. **None are needed for this
  investigation:** GitHub, Datadog, PagerDuty, Amplitude, Asana, Atlassian, ClickUp, Figma,
  Fireflies, Intercom, Linear, monday, Notion, Pendo, Similarweb, Slack.
