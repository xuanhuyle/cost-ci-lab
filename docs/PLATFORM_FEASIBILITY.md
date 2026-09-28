# Platform feasibility: what Snowflake, Databricks, BigQuery and dbt actually expose

Phase 1 deliverable. Research date 2026-09-28. Every row comes from official vendor documentation,
fetched that day. The raw notes carry full quotes, exact column names and about 300 source URLs:
[`research/snowflake.md`](research/snowflake.md), [`research/databricks.md`](research/databricks.md),
[`research/bigquery.md`](research/bigquery.md) and [`research/dbt_and_prior_art.md`](research/dbt_and_prior_art.md).
Evidence labels: `DOCUMENTED` means the vendor docs say it; `INFERRED` is our reasoning; `UNCONFIRMED`
means we could not verify it from a primary source. Classes:
**DM** = directly measured by the platform, **DER** = derived from measured values plus documented
rules, **EST** = estimate, upper bound or allocation, **N/A** = unavailable.

## 1. Bottom line

1. **Only one pricing regime has a native pre-execution cost primitive: BigQuery on-demand.** A dry
   run is free and returns the bytes a query would process. Under on-demand pricing that is the bill,
   before rounding and 10 MB minimums. It is an *upper bound*, though, and it breaks for clustered
   tables, row-level security, external tables and multi-statement scripts. Those scripts include
   dbt `insert_overwrite` incremental builds (`DOCUMENTED`).
2. **No pre-execution cost estimate exists for time-billed compute.** That covers Snowflake credits,
   Databricks DBUs and BigQuery editions slots (`DOCUMENTED`):
   - Snowflake `EXPLAIN` gives upper-bound partitions and bytes, with no time or credits.
   - Databricks `EXPLAIN COST` gives optimizer statistics only.
   - Google states that under capacity pricing "it is not possible to estimate the exact cost of an
     individual query before execution".

   So for most warehouse spend, a pre-merge number must come from **executing** the change (A/B) or
   from **history plus a model**.
3. **The billed object is the capacity pool, not the query.**
   - Snowflake bills warehouse *uptime*: per second, with a 60 s minimum per resume, and idle time
     billed until auto-suspend (default 600 s).
   - Databricks SQL warehouses bill uptime per warehouse-hour.
   - BigQuery editions bill *allocated* slots: baseline plus autoscale in 50-slot steps, each held at
     least 60 s.

   Per-query "cost" is an allocation on all three. Snowflake's `QUERY_ATTRIBUTION_HISTORY` excludes
   idle time, cloud services and serverless features. Databricks has no per-query cost for SQL
   warehouses. BigQuery editions has no per-job $. The marginal $ of a change is
   therefore `bill(pool with change) − bill(pool without)`, which depends on schedule, concurrency and
   idle capacity (`INFERRED` from the documented rules). This is hypothesis HD, tested in Experiment 2.
4. **Post-hoc telemetry for building production baselines is good on all three.**
   - Per-statement metrics exist everywhere, and dbt can tag its queries on each platform (Snowflake
     `query_tag` or comments, BigQuery job labels, Databricks `@@dbt_model_name` query tags).
   - Latency to *metrics* is minutes to about 1 h. Latency to *$-level* data is 3–24 h (`DOCUMENTED`).
   - This is enough for baselines and post-merge calibration, but not for a synchronous CI check that
     needs a just-run CI query's cost. For that, CI must read execution metrics (execution time,
     bytes, task time) directly, not the billing views.
5. **Effective (negotiated) prices:**
   - Snowflake: visible only to organisation billing roles (`RATE_SHEET_DAILY`).
   - Databricks: *nowhere*; system tables hold list price only.
   - BigQuery: only in the billing export (≈1 day latency).

   Dollar outputs therefore require customer configuration (`DOCUMENTED`).
6. **dbt is the right attribution spine, with measurable blind spots.**
   - `state:modified` compares raw (unrendered) SQL text and config. It misses changes in `var` and
     `env_var` values, target-dependent Jinja and data-dependent SQL (`DOCUMENTED`; dbt-core#4304
     open). We confirmed this in code (E-004); scenario s24 tests it empirically.
   - Only dbt-bigquery returns cost statistics (`bytes_billed`, `slot_ms`) in `run_results`
     (`DOCUMENTED-SRC`).
   - Incremental models compile and run their full-refresh branch in a fresh CI schema unless they are
     cloned first (`DOCUMENTED`).

## 2. Primitive comparison

| Primitive | Snowflake | Databricks | BigQuery |
|---|---|---|---|
| Query/job execution history | `ACCOUNT_USAGE.QUERY_HISTORY` (45 min, 365 d); `INFORMATION_SCHEMA.QUERY_HISTORY*` (real time, 7 d) — **DM** | `system.query.history` (≤1 h, 365 d, GA 2026-09-21; SQL warehouses + serverless only); Query History API (near real time) — **DM** | `INFORMATION_SCHEMA.JOBS*` ("near real-time", 180 d) — **DM** |
| Plan / execution profile | `EXPLAIN` (compile-only, upper-bound bytes) **EST**; `GET_QUERY_OPERATOR_STATS` on completion, 14 d — **DM** | `EXPLAIN COST` (stats if collected) **EST**; query profile (UI/JSON) — **DM** | No EXPLAIN; `job_stages`/`timeline` after execution — **DM** |
| Bytes read / scanned / billed | `bytes_scanned`, partitions scanned/total — **DM** (not a billing unit) | `read_bytes`, pruned files — **DM** (not a billing unit) | `total_bytes_processed` / `total_bytes_billed` — **DM**; billed bytes → $ exact on-demand |
| Compute duration | `execution_time`, queued times — **DM** | `total_task_duration_ms`, `execution_duration_ms` — **DM** | `total_slot_ms`, elapsed — **DM** |
| Warehouse/cluster/serverless usage | `WAREHOUSE_METERING_HISTORY` hourly credits (3 h) — **DM** | `system.billing.usage` DBUs per SKU × resource × hour (≤12–24 h) — **DM** | `RESERVATIONS_TIMELINE` per-second autoscale slots (real time) — **DM** |
| Query/job-level cost | `QUERY_ATTRIBUTION_HISTORY.CREDITS_ATTRIBUTED_COMPUTE`: excludes idle, cloud services, serverless and queries ≤~100 ms; 8 h — **EST (allocation)**. Adaptive warehouses: `QUERY_METERING_HISTORY` per query (1 h) — **DM** | Serverless jobs and job compute: DBUs per `job_run_id` — **DM** (DBUs only; classic VM excluded). SQL warehouse queries — **N/A** (apportion) | On-demand: bytes billed × rate — **DER** (exact). Editions: **N/A** (allocation only) |
| Billing tables | `METERING_DAILY_HISTORY` (incl. cloud-services adjustment) — **DM** | `system.billing.usage` — **DM** (list-priced) | Billing export (standard/detailed; ≈1 day, no guarantee) — **DM** |
| List / effective prices | Consumption table (list); `ORGANIZATION_USAGE.RATE_SHEET_DAILY.EFFECTIVE_RATE` (org billing role, ≤24 h) — **DM** | `system.billing.list_prices` (list) **DM**; negotiated **N/A** | Pricing page (list); billing export `cost`/`credits` — **DM** |
| Query/job identifiers | `query_id`, `query_hash`, `query_parameterized_hash` (ignore comments) — **DM** | `statement_id`, `query_source.job_info` — **DM** | `job_id`, `query_info.query_hashes.normalized_literals` — **DM** |
| Tags / labels / metadata | `QUERY_TAG` (dbt `query_tag` config), appended dbt comment — **DM** | `query_tags` (Public Preview; dbt-databricks ≥1.11 auto-tags `@@dbt_model_name`); cluster/warehouse custom tags in billing — **DM** | Job labels (dbt `query-comment: {job-label: true}`); labels flow to billing — **DM** |
| Execution frequency / workload history | Count per `query_parameterized_hash`; `TASK_HISTORY` — **DER** | `system.lakeflow.job_run_timeline`; query history — **DER** | Count per normalized hash; scheduled queries — **DER** |
| Consumers of a table (lineage) | `ACCESS_HISTORY` (Enterprise; 3 h) — **DM** | `system.access.table_lineage` (best effort) — **DM** | `JOBS.referenced_tables` — **DM** |
| Isolated CI compute | Dedicated warehouse (fixed size, `AUTO_SUSPEND=60`, single cluster) — **DM** | Dedicated tagged serverless warehouse; job clusters per run — **DM** | Per-query `reservation` override / `none` = on-demand; `maximumBytesBilled` guard — **DM** |
| Cloning | Zero-copy `CLONE` (metadata-only; **shared DBs such as SNOWFLAKE_SAMPLE_DATA cannot be cloned**) | Delta `SHALLOW CLONE` (UC constraints: managed→managed, no clone-of-clone, VACUUM hazards) | Table clones (no storage until changed; queries still bill bytes) |
| Dry run / cost estimate | **N/A**. Only `SYSTEM$ESTIMATE_*` for QAS (already-run queries), clustering (±100%) and search optimisation | **N/A** | Dry run: bytes only, free — **EST (upper bound)**; no slot estimate |
| Caching | Result cache 24 h (`USE_CACHED_RESULT=FALSE`); warehouse SSD cache dropped on suspend | Result cache (`use_cached_result=false`); **disk cache cannot be disabled** on SQL warehouses/serverless | Query cache 24 h (`useQueryCache=false`); cached results not billed |
| Shared-compute attribution | Idle = metered − attributed (documented recipe); concurrent queries split by undisclosed weighting — **DER/EST** | Documented as not exact on shared all-purpose clusters; warehouse cost must be apportioned — **EST** | Reservation cost apportioned via JOBS_TIMELINE × RESERVATIONS_TIMELINE; "Analysis Slots Attribution" line — **EST** |
| Autoscaling | Multi-cluster Standard/Economy (no numeric Standard timing published) | Classic/pro: queue-time thresholds (2–6 min → +1 cluster …; 15 min to scale down); serverless: ML-predicted IWM | Autoscaler: 50-slot steps, ≥60 s hold (or opt-in "fluid scaling") |
| Capacity / reservations | Capacity contracts (discount on credit price); Gen2 1.25–1.35× rate; Interactive warehouses 60-min minimum | Committed-use (DBCU on Azure); performance vs standard serverless mode | Baseline slots always billed; 1y/3y slot commitments; spend-based CUDs; idle-slot sharing |
| Telemetry latency | IS: none; AU: 45 min–8 h; org $: 24–72 h | Query history ≤1 h; billing ≤12–24 h | JOBS near-real-time; reservations real time; billing ≈1 day |
| dbt state / manifest / lineage | Same for all adapters: `manifest.json` `depends_on`, `state:modified[+]`, `--defer`, `dbt clone` (zero-copy on Snowflake, Databricks, BigQuery) | ← | ← |
| Incremental models | `is_incremental()` is true only if the target exists in the compile target; CI needs `dbt clone` of incremental models to reproduce the recurring branch (`DOCUMENTED`, and reproduced in our harness, E-003) | ← | ← (plus: BigQuery merge scans the destination; dry runs cannot price insert_overwrite scripts) |

## 3. Units are not dollars: when each converts

| Unit | Converts to marginal $ when | Does **not** convert when |
|---|---|---|
| BigQuery bytes billed | On-demand pricing: `bytes/2^40 × $6.25` (US), after MB rounding and the 10 MB/table/query minimums; the first 1 TiB/month is free | The project runs on editions/reservations (bytes are "informational only"); BI Engine-accelerated stages bill 0 bytes; clustered tables make the dry-run value an upper bound |
| BigQuery slot-ms | Never directly: editions bill **allocated** slots | Baseline slots are prepaid (marginal $0 until saturation); autoscale rounds up to 50 slots and holds ≥60 s; slot-ms varies run to run (history-based optimisation, retries, fair scheduling) |
| Snowflake execution time × size rate | Dedicated warehouse, one workload, long runs (≫60 s), where the idle tail is policy-constant | Shared warehouse (the query runs inside uptime already paid for); short runs (60 s minimum per resume); gaps shorter than auto-suspend (idle tail dominates); multi-cluster scale-out (step function) |
| Snowflake attributed credits | = the allocation Snowflake reports; ≈ marginal only for dedicated, saturated warehouses | Excludes idle time, so it understates the true pool cost; concurrency weighting is undisclosed; queries ≤100 ms dropped |
| Databricks DBUs | Serverless jobs (DBUs per run include the VM); list price × customer discount (configured) | Classic compute: cloud VM/disk/network are billed by the cloud provider, outside Databricks; SQL warehouses bill uptime (idle until auto-stop, 10–45 min defaults); shared all-purpose clusters cannot be split |
| Runtime (any platform) | Pools that bill per second of the query's own compute with no idle or minimum (serverless per-query, Snowflake Adaptive warehouses, Databricks serverless jobs, approximately) | Any provisioned pool; any warehouse whose billing is dominated by minimums, idle or concurrency |

## 4. Implications for Cost CI design (`INFERRED` from the above)

- **Strategy D (native estimator)** is viable only for BigQuery on-demand. It is already packaged
  as open source (`dbt-costgate`: state:modified + dry run × list price), so it is commodity.
- **Strategies B, C and E (execution plus history)** are the only routes for Snowflake, Databricks
  and BigQuery editions. Their feasibility is exactly what the lab tests (H2, H3).
- **The economic translation cannot be per-query arithmetic.** It must model the capacity pool
  (schedule, idle tail, minimum billing, concurrency, prepaid baseline). The inputs exist on all
  three platforms (warehouse events and metering, `RESERVATIONS_TIMELINE`, `warehouse_events`), but
  the model is ours to build and validate. This is the most defensible technical component, and
  also the most assumption-laden.
- **CI isolation is possible on all three, with caveats.** Pin warehouse size and generation,
  disable result caches, interleave A/B runs and discard warm-up runs. Databricks' disk cache cannot
  be disabled, and Snowflake Optima and BigQuery history-based optimisation mean a first CI run is
  not steady state (`DOCUMENTED`).
- **Telemetry latency favours a design in which CI reads execution metrics synchronously and
  reconciles $ asynchronously.** Post-merge calibration (H4) can use the $-level views, with 3–24 h
  delay.

## 5. Choice of first platform (input to Phase 3)

| Criterion | Snowflake + dbt | Databricks + dbt | BigQuery + dbt |
|---|---|---|---|
| Tests the *hard* question (time-billed compute, pool economics) | **Yes**: uptime billing, 60 s minimum, idle and multi-cluster are all documented | Yes, but hourly billing grain and ≤12–24 h latency blur experiments | Only under editions; on-demand is solved by dry run |
| Per-run ground truth for a CI experiment | Execution time (real time) + attributed credits (8 h) + warehouse metering (3 h) | Task time (≤1 h) + DBUs per warehouse-hour (≤12–24 h) | Bytes billed (exact, on-demand); slot-ms (noisy) |
| Controlled CI conditions | Dedicated warehouse, result cache off, zero-copy clone | Disk cache cannot be disabled | Cache off; on-demand isolation trivial |
| Production-scale free data | TPC-H SF1–SF1000, TPC-DS 10/100 TB in every account (not clonable; CTAS needed) | `samples.tpch` / `tpcds_sf1000` | Public datasets (no documented TPC-H) |
| Cheap access | 30-day trial with $400 credits, no card | 14-day trial ($400); Free Edition (serverless-only, quota) | Sandbox (1 TiB/month) / free tier |

**Decision: Snowflake + dbt is the first live platform**, backed by the evidence above.
- It is the cleanest test of the hard, non-commodity question: can the recurring cost of a change on
  time-billed compute be predicted before merge?
- Its billing rules are fully documented and simulable. It offers per-second execution metrics
  immediately, and production-scale TPC-H at several scale factors, which a scale-transfer
  experiment needs.

BigQuery on-demand is kept as a **control**. There the answer is already known to be "yes, via dry
run", so it bounds the easy end. Databricks is analysed for portability (Phase 12) but is a weaker
first experiment: hourly billing grain, 12–24 h billing latency and an uncontrollable disk cache.

Without credentials, the executable experiment runs in a local lab: DuckDB, real dbt, TPC-H. The
workload structure is identical to what would run on Snowflake's TPC-H sample data, so the live run
is a configuration change (see `docs/EXPERIMENT_DESIGN.md` and `live/snowflake/`).
