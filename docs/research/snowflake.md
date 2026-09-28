# Snowflake primitives for pre-merge cost estimation (Cost CI)

Research date: 2026-09-28. All pages were fetched that day from docs.snowflake.com, the Snowflake Service Consumption
Table PDF ("Effective: September 25, 2026"), snowflake.com and docs.getdbt.com. Section 10 lists the URLs.
**Evidence labels** (project vocabulary): every statement is `DOCUMENTED` (quoted or paraphrased from the cited primary
source) unless it is marked `INFERRED` (my reasoning from cited facts) or `UNCONFIRMED` (I looked and could not confirm it
from a primary source; treat it as `UNVALIDATED`). Primitive classes: `DIRECTLY_MEASURED` = reported by Snowflake from
execution or metering; `DERIVED` = computed from measured values plus documented rules; `ESTIMATED` = a prediction, upper
bound or heuristic; `UNAVAILABLE` = not exposed.

## 1. Summary
- **No native pre-execution cost estimate** exists for warehouse queries (`UNAVAILABLE`). EXPLAIN is compile-only and gives upper-bound partitionsAssigned/bytesAssigned with no time or credits. The only `SYSTEM$ESTIMATE_*` functions cover QAS (already-run queries), clustering and search optimization.
- **Per-query attribution exists**: `ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY.CREDITS_ATTRIBUTED_COMPUTE`. It excludes idle time, cloud services, serverless,
  storage, transfer and AI. It omits queries of ~100 ms or less and Adaptive Warehouses. Latency is up to 8 h. Concurrent queries are split by an undisclosed "weighted average".
- Billing is **warehouse uptime**: per-second, 60-s minimum per resume, and idle time until auto-suspend (default 600 s). So a change's marginal $ depends on
  schedule and concurrency, not query cost alone (`INFERRED`).
- 2025–26 additions: **Adaptive Warehouses** (GA 2026-06-16; query-based billing; per-query credits in `QUERY_METERING_HISTORY`, ≤1 h; no published formula).
  **Gen2** costs 1.25–1.35× Gen1 per hour (`INFERRED` from the rate table), and QAS is on by default for new Gen2 and multi-cluster warehouses. Also `QUERY_INSIGHTS`, `TABLE_QUERY_PRUNING_HISTORY` and `EXPLAIN CHANGES` (dynamic tables).
- Latency: INFORMATION_SCHEMA has none but keeps 7–14 days. ACCOUNT_USAGE ranges from 45 min (QUERY_HISTORY) through 3 h (WAREHOUSE_METERING_HISTORY) to 8 h (attribution).
  The effective $/credit is in ORGANIZATION_USAGE.RATE_SHEET_DAILY (≤24 h; org/billing roles only).
- Gaps: no cost model, allocated attribution, no per-query idle or concurrency figure, shared DBs (SNOWFLAKE_SAMPLE_DATA) not clonable, and CS credits shown before the 10% adjustment.

## 2. Primitive table

| Primitive | Object/API (exact names) | Granularity | Latency & retention | Classification | Conditions for converting to $ | Source |
|---|---|---|---|---|---|---|
| Query execution metrics | `ACCOUNT_USAGE.QUERY_HISTORY`: `execution_time`, `total_elapsed_time`, `compilation_time`, `queued_provisioning_time`, `queued_repair_time`, `queued_overload_time`, `transaction_blocked_time`, `bytes_scanned`, `percentage_scanned_from_cache` (0.0–1.0), `partitions_scanned`, `partitions_total`, `bytes_spilled_to_local_storage`, `bytes_spilled_to_remote_storage`, `bytes_written`, `rows_inserted/updated/deleted`, `query_load_percent`, `warehouse_name/size/type`, `cluster_number`, `query_tag`, `query_hash`, `query_parameterized_hash`, `query_retry_time`, `query_retry_cause`, `fault_handling_time`, `query_acceleration_bytes_scanned`, `query_text` (truncated at 100K chars) | per statement | ≤45 min; 365 days | DIRECTLY_MEASURED | Time × size rate is **not** a bill. Billing is warehouse uptime (60-s minimum, idle, concurrency). Needs a warehouse-level model plus the $/credit | sql-reference/account-usage/query_history |
| Per-query cloud services | `QUERY_HISTORY.credits_used_cloud_services` | per statement | as above | DIRECTLY_MEASURED (pre-adjustment) | "does not take into account the adjustment for cloud services, and may therefore be greater than the credits that are billed". Billed only if daily CS > 10% of daily warehouse credits | account-usage/query_history; user-guide/cost-understanding-compute |
| Near-real-time query metrics | `INFORMATION_SCHEMA.QUERY_HISTORY()`, `QUERY_HISTORY_BY_SESSION/_BY_USER/_BY_WAREHOUSE`. The documented output **lacks** `partitions_*`, `bytes_spilled_*`, `percentage_scanned_from_cache`, `query_load_percent` | per statement | no latency; 7 days; `RESULT_LIMIT` 1–10,000 (default 100), applied **before** WHERE | DIRECTLY_MEASURED | as QUERY_HISTORY. Seeing other users' queries needs MONITOR/OPERATE on the warehouse | sql-reference/functions/query_history |
| Per-query attributed compute | `ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY`: `QUERY_ID`, `PARENT_QUERY_ID`, `ROOT_QUERY_ID`, `WAREHOUSE_ID`, `WAREHOUSE_NAME`, `QUERY_HASH`, `QUERY_PARAMETERIZED_HASH`, `QUERY_TAG`, `USER_NAME`, `START_TIME`, `END_TIME`, `CREDITS_ATTRIBUTED_COMPUTE`, `CREDITS_USED_QUERY_ACCELERATION` | per query (> ~100 ms) | ≤8 h; 365 days; complete from mid-Aug 2024. ORG premium view: 3 h, organization account only | DERIVED (Snowflake allocation: "weighted average of their resource consumption during a given time interval", "inclusive of any resizing and/or autoscaling") | Excludes idle time, data transfer, storage, cloud services, serverless and AI tokens. Not for Adaptive Warehouses. The accelerated query total = the two credit columns summed. × effective rate | account-usage/query_attribution_history; user-guide/cost-attributing |
| Per-query metered credits (Adaptive only) | `ACCOUNT_USAGE.QUERY_METERING_HISTORY`: `QUERY_ID`, `WAREHOUSE_ID/NAME`, `QUERY_METERING_HOUR`, `QUERY_START_TIME`, `QUERY_END_TIME`, `PARENT_/ROOT_QUERY_ID`, `USER_ID/NAME`, `ROLE_NAME`, `QUERY_HASH`, `QUERY_PARAMETERIZED_HASH`, `QUERY_TAG`, `CREDITS_USED_COMPUTE`, `CREDITS_USED_CLOUD_SERVICES`, `CREDITS_USED` | per query per metering hour | ≤1 h; 365 days; running rows are updated in place | DIRECTLY_MEASURED | Enterprise + Adaptive only. QAS is included in compute. "extremely low or zero credit usage might not be included" | account-usage/query_metering_history; user-guide/warehouses-adaptive |
| Warehouse metering | `ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY`: `START_TIME`, `END_TIME`, `WAREHOUSE_ID`, `WAREHOUSE_NAME`, `CREDITS_USED` (=compute+CS), `CREDITS_USED_COMPUTE`, `CREDITS_USED_CLOUD_SERVICES`, `CREDITS_ATTRIBUTED_COMPUTE_QUERIES` | hourly per warehouse | ≤3 h (the CS column ≤6 h); 365 days. IS table function: 6 months, "generally deprecated", excludes Adaptive. ORG/READER: ≤24 h | DIRECTLY_MEASURED | CREDITS_USED is pre-adjustment. Use `ALTER SESSION SET TIMEZONE = UTC` to reconcile with ORG views | account-usage/warehouse_metering_history; functions/warehouse_metering_history |
| Idle credits | Documented example: `SUM(credits_used_compute) - SUM(credits_attributed_compute_queries)` per warehouse | hourly per warehouse | ≤3 h | DERIVED | NULL attributed column for Adaptive. Docs recommend spreading idle in proportion to usage | account-usage/warehouse_metering_history; cost-attributing |
| Billed daily credits | `ACCOUNT_USAGE.METERING_DAILY_HISTORY`: `SERVICE_TYPE`, `USAGE_DATE`, `CREDITS_USED_COMPUTE`, `CREDITS_USED_CLOUD_SERVICES`, `CREDITS_USED`, `CREDITS_ADJUSTMENT_CLOUD_SERVICES` (negative), `CREDITS_BILLED` | daily per service type | ≤3 h; 365 days (ORG ≤2 h) | DIRECTLY_MEASURED | The only place the CS adjustment appears. × daily effective rate | account-usage/metering_daily_history |
| Compile-time plan | `EXPLAIN [USING {TABULAR\|JSON\|TEXT}]`: `step`, `id`, `parentOperators`, `operation`, `objects`, `alias`, `expressions`, `partitionsTotal`, `partitionsAssigned`, `bytesAssigned`, and a `GlobalStats` row; also `SYSTEM$EXPLAIN_PLAN_JSON` | per operator | synchronous; not persisted | ESTIMATED ("upper bound estimates"; "join pruning can reduce" actual) | No time or credits. Needs a learned bytes→time→credits model. Uses no warehouse, but compilation uses CS credits. The plan "might differ depending on the size of the current warehouse" (XSMALL is assumed when none is set) | sql-reference/sql/explain |
| Post-execution operator stats | `TABLE(GET_QUERY_OPERATOR_STATS(<query_id>))`: `QUERY_ID`, `STEP_ID`, `OPERATOR_ID`, `PARENT_OPERATORS`, `OPERATOR_TYPE`, `OPERATOR_STATISTICS` (`io.bytes_scanned`, `io.percentage_scanned_from_cache`, `pruning.partitions_scanned/partitions_total/partitions_pruned_by_snowflake_optima`, `spilling.bytes_spilled_local_storage/remote_storage`, `network.network_bytes`, `input_rows`, `output_rows`, `dml.*`), `EXECUTION_TIME_BREAKDOWN` (`overall_percentage`, `initialization`, `processing`, `synchronization`, `local_disk_io`, `remote_disk_io`, `network_communication`), `OPERATOR_ATTRIBUTES` | per operator | as soon as the query completes; queries from the past 14 days; needs OPERATE or MONITOR on the warehouse | DIRECTLY_MEASURED | Time is split as a percentage only; no credits | functions/get_query_operator_stats |
| Query Profile (Snowsight) | Query History » Query Profile: the same statistics plus a Query Insights pane | per operator | 14 days; "best-effort basis and is not guaranteed for all queries" | DIRECTLY_MEASURED | UI only | user-guide/ui-snowsight-activity |
| Query insights | `ACCOUNT_USAGE.QUERY_INSIGHTS`: `start_time`, `end_time`, `total_elapsed_time`, `query_id`, `query_hash`, `query_parameterized_hash`, `warehouse_id`, `warehouse_name`, `insight_instance_id`, `insight_type_id` (for example `QUERY_INSIGHT_REMOTE_SPILLAGE`, `QUERY_INSIGHT_EXPLODING_JOIN`, `QUERY_INSIGHT_QUEUED_OVERLOAD`, `QUERY_INSIGHT_NO_FILTER_ON_TOP_OF_TABLE_SCAN`), `message`, `suggestions`, `is_opportunity`, `insight_topic` | per insight | ≤90 min; 365 days (ORG 3.5 h) | DERIVED (heuristic flags) | No $. Not produced for multi-step plans, secure objects, hybrid tables, EXPLAIN or reused results | account-usage/query_insights; user-guide/query-insights |
| Pruning history | `ACCOUNT_USAGE.TABLE_QUERY_PRUNING_HISTORY` / `COLUMN_QUERY_PRUNING_HISTORY`: `NUM_QUERIES`, `AGGREGATE_QUERY_ELAPSED_TIME`, `..._COMPILATION_TIME`, `..._EXECUTION_TIME`, `PARTITIONS_SCANNED`, `PARTITIONS_PRUNED`, `ROWS_SCANNED`, `ROWS_PRUNED`, `ROWS_MATCHED`, by `QUERY_HASH`/`QUERY_PARAMETERIZED_HASH` | hourly × table × hash × warehouse | ≤4 h; 1 year | DIRECTLY_MEASURED (aggregated) | No credits. Needs USAGE_VIEWER | account-usage/table_query_pruning_history |
| Lineage / consumers | `ACCOUNT_USAGE.ACCESS_HISTORY`: `query_id`, `query_start_time`, `user_name`, `direct_objects_accessed`, `base_objects_accessed`, `objects_modified`, `object_modified_by_ddl`, `policies_referenced`, `parent_query_id`, `root_query_id`, `event_source`. JSON has `objectDomain`, `objectName`, `objectId`, `columns[]` and column lineage `directSources`/`baseSources` | per query | ≤3 h; 365 days; **Enterprise Edition**; parent/root IDs only from 2024-01-15/16 | DIRECTLY_MEASURED | Join on `query_id` to QUERY_ATTRIBUTION_HISTORY to cost downstream readers. Failed queries are not recorded, and not every QUERY_HISTORY row is recorded | account-usage/access_history |
| View dependencies | `ACCOUNT_USAGE.OBJECT_DEPENDENCIES` | per edge | ≤3 h | DIRECTLY_MEASURED | "Data movement ... does not result in an object dependency", so dbt-built tables are not linked | account-usage/object_dependencies |
| Scheduled run frequency | `ACCOUNT_USAGE.TASK_HISTORY`: `NAME`, `QUERY_ID`, `SCHEDULED_TIME`, `COMPLETED_TIME`, `STATE`, `ROOT_TASK_ID`, `RUN_ID`, `GRAPH_RUN_GROUP_ID`, `ATTEMPT_NUMBER`, `QUERY_HASH`, `QUERY_PARAMETERIZED_HASH`; also `COMPLETE_TASK_GRAPHS` | per run | ≤45 min; 365 days. IS `TASK_HISTORY`: 7 days | DIRECTLY_MEASURED | Cost via QUERY_ATTRIBUTION (user-managed tasks) or SERVERLESS_TASK_HISTORY | account-usage/task_history |
| Serverless task credits | `ACCOUNT_USAGE.SERVERLESS_TASK_HISTORY`: `START_TIME`, `END_TIME`, `CREDITS_USED`, `TASK_ID`, `TASK_NAME`, `SCHEMA_*`, `DATABASE_*` | per task per window | ≤3 h; 365 days. IS: 14 days | DIRECTLY_MEASURED | × rate. `CREDITS_USED` = "credits billed", so the 0.9/1 multipliers are presumably already applied (`INFERRED`) | account-usage/serverless_task_history |
| Recurrence grouping | `query_hash`/`query_parameterized_hash` (and `*_version`) in QUERY_HISTORY, QUERY_ATTRIBUTION_HISTORY, TASK_HISTORY, QUERY_ACCELERATION_ELIGIBLE, QUERY_INSIGHTS; `AGGREGATE_QUERY_HISTORY` (`CALLS` per 1-minute interval); Snowsight "Grouped Queries" | per hash per period | AGGREGATE view 3 h; Grouped Queries 14 days | DERIVED (frequency = count per hash) | Hashes ignore case-insensitive identifiers, whitespace and **comments**. Hash logic is versioned | user-guide/query-hash; account-usage/aggregate_query_history |
| Dynamic-table refresh | `DYNAMIC_TABLE_REFRESH_HISTORY` (3 h; 1 year); `EXPLAIN CHANGES <ddl>` → `effects[].properties.effective_refresh_action` ∈ {NO_DATA, REINITIALIZE, FULL, INCREMENTAL, CUSTOM_INCREMENTAL, CREATE, FAILURE}, `effective_refresh_action_reason` | per refresh / per DDL | EXPLAIN CHANGES GA 2026-09-15 | DIRECTLY_MEASURED / ESTIMATED (qualitative; no credits) | The prediction "reflects the state ... at the moment EXPLAIN CHANGES runs" and covers only the targeted DT | user-guide/dynamic-tables/predict-refresh |
| dbt Projects on Snowflake runs | `ACCOUNT_USAGE.DBT_PROJECT_EXECUTION_HISTORY` (`QUERY_ID`, `COMMAND`, `ARGS`, `STATE`, `WAREHOUSE_NAME`, `DBT_VERSION`, ...) | per execution | ≤2 h; 365 days (IS: 7 days) | DIRECTLY_MEASURED | No credit columns | account-usage/dbt_project_execution_history |
| Effective $/credit | `ORGANIZATION_USAGE.RATE_SHEET_DAILY`: `DATE`, `ORGANIZATION_NAME`, `CONTRACT_NUMBER`, `ACCOUNT_NAME`, `ACCOUNT_LOCATOR`, `REGION`, `SERVICE_LEVEL`, `USAGE_TYPE`, `CURRENCY`, `EFFECTIVE_RATE` ("after applying any applicable discounts"), `SERVICE_TYPE`, `RATING_TYPE`, `BILLING_TYPE`, `IS_ADJUSTMENT` | daily per account × service | ≤24 h; kept indefinitely; "can change" until month close | DIRECTLY_MEASURED | Needs the organization account (GLOBALORGADMIN or `ORGANIZATION_BILLING_VIEWER`) or an ORGADMIN-enabled account. Not for reseller contracts | organization-usage/rate_sheet_daily; sql-reference/organization-usage |
| Cost in currency | `ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY`: `USAGE_DATE`, `ACCOUNT_NAME`, `USAGE`, `USAGE_IN_CURRENCY`, `CURRENCY`, `BALANCE_SOURCE` (capacity/rollover/free usage/overage/rebate), `BILLING_TYPE`, `RATING_TYPE`, `SERVICE_TYPE`, `IS_ADJUSTMENT` | daily | ≤72 h; kept indefinitely | DIRECTLY_MEASURED | Same access limits; `REMAINING_BALANCE_DAILY` (72 h) holds the capacity balance | organization-usage/usage_in_currency_daily |
| List prices / rates | Service Consumption Table: Table 1(a)–(e) credits/hour, Table 2(a) on-demand $/credit, Table 5 serverless multipliers | static | effective 2026-09-25 | DERIVED (published list; exact on-demand, upper bound for capacity) | Capacity price = on-demand × (1 − Platform Credit Discount in the Order Form) | CreditConsumptionTable.pdf |
| Pre-execution query cost | none. The complete function list has only `SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_COSTS`, `SYSTEM$ESTIMATE_QUERY_ACCELERATION`, `SYSTEM$ESTIMATE_SEARCH_OPTIMIZATION_COSTS`. EXPLAIN has no cost fields | — | — | **UNAVAILABLE** | Build a model from EXPLAIN bytes and history | sql-reference/functions-all; sql/explain |
| QAS what-if | `SYSTEM$ESTIMATE_QUERY_ACCELERATION('<query_id>')` → `estimatedQueryTimes` per scale factor, `originalQueryTime`, `upperLimitScaleFactor`, `status`, `ineligibleReason`; view `QUERY_ACCELERATION_ELIGIBLE` (`ELIGIBLE_QUERY_ACCELERATION_TIME`, `UPPER_LIMIT_SCALE_FACTOR`) | per **already executed** query (≤14 days) | view ≤3 h | ESTIMATED (times, not credits) | Needs a scale factor × size rate model | functions/system_estimate_query_acceleration; query-acceleration-service |
| Serverless feature estimates | `SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_COSTS` ("can vary by up to 100% (or, in rare cases, several times)"); `SYSTEM$ESTIMATE_SEARCH_OPTIMIZATION_COSTS` ("up to 50% (or, in rare cases, by several times)"); `AI_COUNT_TOKENS` (token estimate) | per table / prompt | on demand | ESTIMATED | Returns credits (and TB for storage) | functions/system_estimate_* |
| Warehouse load & events | `WAREHOUSE_LOAD_HISTORY` (`AVG_RUNNING`, `AVG_QUEUED_LOAD`, `AVG_QUEUED_PROVISIONING`, `AVG_BLOCKED`; 5-min intervals); `WAREHOUSE_EVENTS_HISTORY` (resume/suspend/resize, cluster start/stop; `EVENT_NAME`, `EVENT_REASON`, `CLUSTER_NUMBER`, `SIZE`, `RESOURCE_CONSTRAINT`) | 5 min / per event | ≤3 h; 1 year (IS load: 14 days) | DIRECTLY_MEASURED | Inputs for idle and concurrency modelling | account-usage/warehouse_load_history; warehouse_events_history |
| QAS credits per warehouse | `ACCOUNT_USAGE.QUERY_ACCELERATION_HISTORY` (`CREDITS_USED`, `WAREHOUSE_*`) | per warehouse per window | ≤3 h; 1 year; Enterprise | DIRECTLY_MEASURED | × rate | account-usage/query_acceleration_history |
| Budgets / anomalies | Budgets (monthly credit limit, "projected to be exceeded"; refresh "up to 6.5 hours", 1 h "low latency budget"; per-user quotas GA 2026); `ANOMALIES_DAILY` (3 h; needs ≥30 days of history) | account / group / user | post-hoc | ESTIMATED / DERIVED | Post-hoc controls, not pre-merge | user-guide/budgets; cost-anomalies |

## 3. Billing rules (exact)
**Credits per hour per cluster.** Sources: Consumption Table Tables 1(a), 1(b), 1(d) and docs warehouses-overview.

| Size | XS | S | M | L | XL | 2XL | 3XL | 4XL | 5XL | 6XL |
|---|---|---|---|---|---|---|---|---|---|---|
| Standard Gen1 | 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 | 256 | 512 |
| Gen2 AWS / GCP | 1.35 | 2.7 | 5.4 | 10.8 | 21.6 | 43.2 | 86.4 | 172.8 | n/a | n/a |
| Gen2 Azure | 1.25 | 2.5 | 5 | 10 | 20 | 40 | 80 | 160 | n/a | n/a |
| Interactive warehouse | 0.6 | 1.2 | 2.4 | 4.8 | 9.6 | 19.2 | 38.4 | 76.8 | – | – |

- Snowpark-optimized (Table 1(c)): MEMORY_1X = Gen1 rates (1…128); MEMORY_1X_x86 1.10…140.80; MEMORY_16X M 6, L 12,
  XL 24, 2XL 48, 3XL 96, 4XL 192, 5XL 384, 6XL 768; MEMORY_16X_x86 M 6.25…4XL 200; MEMORY_64X (Preview) L 15…4XL 240;
  MEMORY_64X_x86 (Preview) L 16…4XL 256. The default Snowpark-optimized size is MEDIUM. Gen2 is not available for X5LARGE or X6LARGE.
- Gen2 costs 1.35× Gen1 per hour on AWS/GCP and 1.25× on Azure (`INFERRED` arithmetic). The docs say Gen2 makes "the majority of queries finish
  faster" and tell you to "Conduct tests". Net $ impact is workload-specific.
- **Default generation conflict** (`UNCONFIRMED`): CREATE WAREHOUSE and the Gen2 page say `GENERATION` defaults to `'2'` "unless Gen2 isn't
  available in your region". warehouses-overview says Gen2 is "currently ... not the default". Always set `GENERATION` explicitly.
- **Multi-cluster rate** = size rate × number of running clusters (Consumption Table footnote 2). Multi-cluster needs Enterprise Edition.
- **Per-second billing and minimums**: "credits are billed per-second, with a 60-second (i.e. 1-minute) minimum". "Each time a
  warehouse is started or resumed, the warehouse is billed for 1 minute's worth of usage". A warehouse that runs 30–60 s is billed 60 s. One that runs 61 s is billed 61 s.
  Running 61 s, stopping, then running under 60 s is billed 121 s. Documented Gen1 totals: 0–60 s = 0.017 (XS), 0.267 (XL), 4.268 (5XL) credits.
  "Suspending and then resuming a warehouse within the first minute results in multiple charges". Resizing up bills 1 minute of the
  *additional* resources only (Small→Medium = 1 minute of 2 extra credits/h). Resizing from 5XL/6XL down to 4XL or smaller briefly bills
  both. Generation, type or `RESOURCE_CONSTRAINT` changes while running bill both old and new resources until old queries finish.
  Other minimums from the Consumption Table: **Interactive warehouses have a 60-minute minimum** per start/resume. SPCS compute nodes have 5 minutes.
- **Auto-suspend/resume**: `AUTO_SUSPEND` is in seconds, default **600**. "The background process that suspends a warehouse runs
  approximately every 30 seconds", so values below 30 or not multiples of 30 may not behave as expected. 0/NULL means never suspend.
  `AUTO_RESUME` default TRUE. `INITIALLY_SUSPENDED` default **FALSE**: a new warehouse starts running and metering; with TRUE there is
  "Cost impact: None". Suspend "does not abort any queries": the warehouse quiesces, then shuts down. For multi-cluster warehouses, auto-suspend
  happens only when the minimum cluster count is running and idle.
- **Multi-cluster scaling (Auto-scale mode only)**:
  - **Standard** (default) starts a cluster "When a query is queued, or if Snowflake estimates the currently running clusters don't have enough
    resources". It adds 1 cluster at a time if MAX_CLUSTER_COUNT ≤10, and several at once above 10. It shuts down "After a sustained period of low load",
    after running queries finish.
  - **Economy** starts a cluster "Only if the system estimates there's enough query load to keep the cluster busy for at least 6 minutes". It marks
    the least-loaded cluster for shutdown if it "has less than 6 minutes of work left".
  - The current page gives no numeric timing for Standard (`UNCONFIRMED` whether one exists). Maximized mode (min = max) runs all clusters.
  - Max clusters: XS–M 300, L 160, XL 80, 2XL 40, 3XL 20, 4XL–6XL 10 (default limit 10).
- **Cloud services**: "You will be charged 4.4 Credits per hour of Cloud Services use" (Consumption Table). The charge applies "only if the daily consumption of
  cloud services exceeds 10% of the daily usage of virtual warehouses", calculated daily in UTC. "The daily adjustment never exceeds actual
  cloud services usage". "Serverless compute does not factor into the 10% adjustment". CS for serverless features is multiplied and billed
  inside that feature's line. Capacity accounts pay CS only if their subscription started on or after 2020-02-01. The docs page's worked example
  ("For example:") renders empty today. Use `METERING_DAILY_HISTORY.CREDITS_ADJUSTMENT_CLOUD_SERVICES`.
- **Serverless**: billed in Compute-Hours, "calculated on a per second basis, rounded up to the nearest whole second". One Compute-Hour is
  "comparable to running an XS Virtual Warehouse for one hour", × the feature multiplier (compute / CS). Serverless Tasks 0.9/1; Serverless
  Tasks Flex 0.5/1; Query Acceleration 1/–; Clustering Classic 2/1; Materialized Views 2/1; Search Optimization 2/1; Serverless Alerts
  0.9/1; Replication Classic 2/0.35. Optima Clustering is 0.007 credits per uncompressed GB and Snowpipe is 0.0037 credits per GB.
  - Serverless tasks: max size XXLARGE-equivalent. `SERVERLESS_TASK_MIN_STATEMENT_SIZE` (default XSMALL) and `..._MAX_...` (default XXLARGE).
    The first runs use `USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE` (default MEDIUM). Snowflake then sizes from task history.
  - User-managed tasks bill as warehouse usage "with a 60-second minimum each time the warehouse is resumed".
- **QAS** (Enterprise): "billed by the second, only when the service is in use ... billed separately from warehouse usage". The scale factor caps
  leased compute: for example, a Medium with factor 5 can lease "up to an additional 20 credits per hour". "The cost is the same no matter how many queries
  are using the query acceleration service at the same time". The default factor is 8 when enabled explicitly. It is **2** when QAS is auto-enabled at
  creation of a Gen2 or multi-cluster warehouse, which "enables ... QAS by default". A factor of 0 means no cap. Per-query credits are in
  `CREDITS_USED_QUERY_ACCELERATION`. Changing an existing Gen1 warehouse to Gen2 does not enable QAS.
- **Adaptive Warehouses** (Enterprise+, GA 2026-06-16, select regions): "query-based billing model, where the cost of each query depends on
  factors like the amount of compute and software resources it uses". There is no charge for creating one. `MAX_QUERY_PERFORMANCE_LEVEL` (default XLARGE)
  and `QUERY_THROUGHPUT_MULTIPLIER` (default 2; 0 = unlimited) bound spend. The Consumption Table gives no rate. It says consumption "scales based on
  factors like compute usage, software optimizations, and active queries". Its footnote marks Adaptive as "Preview", which conflicts with the docs' GA (`UNCONFIRMED`).
- **On-demand vs capacity**: On-demand $/credit comes from Table 2(a). For example, AWS US East (N. Virginia) and US West (Oregon) cost Standard $2.00, Enterprise $3.00,
  Business Critical $4.00 and VPS $6.00. AWS EU Dublin costs $2.60/$3.90/$5.20/$7.80. "Capacity Platform Credit Pricing is based on applying the Platform
  Credit Discount in your Order Form to the On Demand Platform Credit Price". The per-account effective $/credit is visible only in
  `RATE_SHEET_DAILY.EFFECTIVE_RATE`. Currency cost is in `USAGE_IN_CURRENCY_DAILY`.

## 4. CI / isolation primitives
- **Zero-copy clone**: `CREATE { DATABASE | SCHEMA } <n> CLONE <src> [ {AT|BEFORE} (TIMESTAMP|OFFSET|STATEMENT => ...) ] [IGNORE TABLES
  WITH INSUFFICIENT DATA RETENTION] [IGNORE HYBRID TABLES] [INCLUDE INTERNAL STAGES]`, and `CREATE TABLE ... CLONE`.
  - A clone "does not contribute to the overall data storage ... until operations are performed on the clone that modify existing data".
  - Cloning and DDL "are entirely metadata operations, meaning they use only cloud services compute".
  - Not cloned: external tables; hybrid tables in a schema clone (a database clone includes them); pipes on internal stages; internal stages unless
    `INCLUDE INTERNAL STAGES` is set (which "incurs compute and file transfer charges" via COPY FILES). User tasks are not cloned with `CREATE SCHEMA ... CLONE ... AT (TIMESTAMP ...)`.
  - A cloned table has no load history. It "starts with Automatic Clustering suspended", and storage lifecycle policies are not attached.
  - The clone of a container does not inherit the container's grants. Child objects inherit theirs. Cloning covers only objects the cloning role can access.
  - **Shared/imported databases cannot be cloned**: "Creating a clone of an imported database or any schemas/tables in the database" and Time
    Travel on it are "not supported". For SNOWFLAKE_SAMPLE_DATA: "No cloning or Time Travel can be performed on the database or any
    schemas/tables". Query it in place, or CTAS into your own database, which incurs storage and compute. The sample database itself does "not incur storage charges".
- **Time Travel**: the default retention is 1 day. Standard Edition allows 0–1. Enterprise+ permanent objects allow 0–90; transient and temporary allow 0 or 1.
  Fail-safe is 7 days for permanent objects and 0 for transient/temporary. `DATA_RETENTION_TIME_IN_DAYS`; the account `MIN_DATA_RETENTION_TIME_IN_DAYS` sets a floor.
  dbt: "By default, all Snowflake tables created by dbt are transient". Dynamic tables are permanent unless `transient`/flag is set.
- **Separate warehouses**: for a dedicated CI warehouse, use `CREATE WAREHOUSE ci_wh WAREHOUSE_SIZE=... GENERATION='1'|'2'
  ENABLE_QUERY_ACCELERATION=FALSE MAX_CLUSTER_COUNT=1 AUTO_SUSPEND=60 INITIALLY_SUSPENDED=TRUE` (`INFERRED` recipe from the documented defaults).
  Set `STATEMENT_TIMEOUT_IN_SECONDS` (default 172800 = 2 days; the lowest non-zero value of session and warehouse wins) and `STATEMENT_QUEUED_TIMEOUT_IN_SECONDS`.
  Resource monitors "work for warehouses only" (not serverless). Their quota counts warehouse and cloud-services credits, and "limits do not take into account the daily 10% adjustment".
  dbt can route models and tests with `snowflake_warehouse`. The docs suggest a dedicated warehouse to "isolate dynamic table costs during testing".
- **Result cache**: a persisted result expires after 24 hours. Each reuse resets it, up to 31 days from first execution. Reuse needs an exact text match
  ("lowercase versus uppercase, or ... table aliases" break it), no non-reusable functions (UUID_STRING, RANDOM, RANDSTR), no external functions,
  no hybrid tables, unchanged data and micro-partitions (reclustering breaks it), and the required privileges. "Meeting all these conditions does not guarantee"
  reuse. Disable it with `ALTER SESSION SET USE_CACHED_RESULT = FALSE` (Session parameter; Account » User » Session; default TRUE).
  Whether a cache hit needs or bills a running warehouse is not stated (`UNCONFIRMED`).
- **Warehouse (local-disk) cache**: "the cache is dropped when the warehouse is suspended". Downsizing drops the cache of the removed resources.
  The hit rate is `percentage_scanned_from_cache`. The docs recommend auto-suspend of ~5 min for DevOps/ad-hoc work, ≥10 min for BI, and "immediate suspension" for tasks.
- **Repeatable benchmark conditions**:
  - The TPC-H sample page recommends a session `query_tag`, `use_cached_result = false`, and running the 22 queries "three times in succession ... then repeat".
  - Operator stats "can return different runtime statistics" across executions. Documented causes are data volume, materialized-view freshness, clustering, cached data,
    warehouse size, "Virtual warehouse initialization time" and external-function latency.
  - QAS "depends on server availability ... performance improvements might fluctuate".
  - Optima Planning (Gen2 and Adaptive; "enabled by default") learns plans from executions. Optima Indexing builds hidden indexes "on a best-effort basis".
    Optima Metadata adds pruning metadata automatically.
  - `INFERRED` practice: pin the generation and QAS, use a single cluster, give the CI warehouse no other workload, and suspend then resume for a cold cache (each resume bills 60 s).
    Record `warehouse_size`, `warehouse_type`, `percentage_scanned_from_cache` and `query_retry_time` per run.

## 5. Attribution primitives
- **QUERY_TAG**: a Session parameter settable at Account » User » Session, a "String (up to 2000 characters)", default none. It appears in QUERY_HISTORY,
  QUERY_HISTORY_BY_*, QUERY_ATTRIBUTION_HISTORY and QUERY_METERING_HISTORY. The docs' pattern is `ALTER SESSION SET QUERY_TAG = 'COST_CENTER=finance'`.
- **Object tags**: schema-level key/value objects, at most 50 tags per object. They can be set on warehouses and users. "Creating and setting tags is available to all
  accounts" (some advanced capabilities need Enterprise). `TAG_REFERENCES` has 2 h latency. The docs' shared-warehouse pattern tags users
  with `cost_center` and joins `TAG_REFERENCES` to `QUERY_ATTRIBUTION_HISTORY` on user name. This works for "a single account at a time".
- **dbt-snowflake query_tag**: the profile can set a default query tag for the connection. Override it with the model config `query_tag` (`+query_tag:` in
  `dbt_project.yml`, or `{{ config(query_tag='...') }}`), or override the `set_query_tag` macro (the docs' example uses `model.name`). dbt runs
  `alter session set query_tag` at the start of each materialization and resets it at the end. "Build failures midway through a
  materialization may result in subsequent queries running with an incorrect tag."
- **dbt query-comment**: by default dbt adds a JSON comment (dbt version, profile, target, `node_id`). "For Snowflake, the comment appears at the end
  of the query. This prevents the comment from being stripped during processing". The dict syntax `append: true` "is useful on databases like
  Snowflake which remove leading SQL comments" (dbt docs).
  - **Snowflake's own docs do not state** that leading comments are stripped from `QUERY_TEXT` (`UNCONFIRMED` from a Snowflake primary source).
    The Python connector's `execute_string`/`execute_stream` has client-side `remove_comments=False` by default.
  - `query_hash` and `query_parameterized_hash` ignore comments, so per-run dbt comments do not split recurrence groups.
  - `QUERY_TEXT` is truncated at 100K characters, so an appended comment on very long SQL may be lost (`INFERRED`).
  - Queries that fail with syntax errors show `<redacted>` text unless `ENABLE_UNREDACTED_QUERY_SYNTAX_ERROR` is set.
- **Hierarchy**: sum `CREDITS_ATTRIBUTED_COMPUTE` over `root_query_id = X OR query_id = X` for stored procedures. The docs find the root through ACCESS_HISTORY.
- **Shared-warehouse idle time**: "The cost per query does not include warehouse idle time. Idle time is a period of time in which no queries
  are running in the warehouse and can be measured at the warehouse level." Documented recipes distribute it "in proportion to their usage":
  attributed_credits = tag_or_user_credits / Σ attributed × Σ `WAREHOUSE_METERING_HISTORY.credits_used_compute`.

## 6. Telemetry latency & retention (maximums as documented; "actual latency ... may be less")
| Object | Latency | Retention / window |
|---|---|---|
| INFORMATION_SCHEMA table functions (general) | none | 7 days to 6 months, varies |
| IS `QUERY_HISTORY*` / `TASK_HISTORY` / `DYNAMIC_TABLE_REFRESH_HISTORY` / `DBT_PROJECT_EXECUTION_HISTORY` | none | 7 days |
| IS `SERVERLESS_TASK_HISTORY`, `WAREHOUSE_LOAD_HISTORY`, `QUERY_ACCELERATION_HISTORY` | none | 14 days |
| IS `WAREHOUSE_METERING_HISTORY` (deprecated; no Adaptive; MONITOR USAGE) | none | 6 months |
| `GET_QUERY_OPERATOR_STATS`, Snowsight Query Profile, `SYSTEM$ESTIMATE_QUERY_ACCELERATION` | on completion | 14 days |
| AU `QUERY_HISTORY`, `TASK_HISTORY`, `COMPLETE_TASK_GRAPHS` | 45 min | 1 year |
| AU `QUERY_METERING_HISTORY` (Adaptive) | 1 h | 1 year |
| AU `QUERY_INSIGHTS` | 90 min (list says blank) | 1 year |
| AU `OBJECT_DEPENDENCIES`, `TAG_REFERENCES` | 3 h / 2 h | current |
| AU `DBT_PROJECT_EXECUTION_HISTORY` | 2 h | 1 year |
| AU `WAREHOUSE_METERING_HISTORY` | 3 h (CS column 6 h) | 1 year |
| AU `METERING_DAILY_HISTORY`, `METERING_HISTORY`, `ACCESS_HISTORY`, `SERVERLESS_TASK_HISTORY`, `WAREHOUSE_LOAD_HISTORY`, `WAREHOUSE_EVENTS_HISTORY`, `QUERY_ACCELERATION_HISTORY`, `QUERY_ACCELERATION_ELIGIBLE`, `DYNAMIC_TABLE_REFRESH_HISTORY`, `AGGREGATE_QUERY_HISTORY`, `ANOMALIES_DAILY` | 3 h | 1 year |
| AU `TABLE_QUERY_PRUNING_HISTORY`, `COLUMN_QUERY_PRUNING_HISTORY` / `TABLE_PRUNING_HISTORY` | 4 h / 6 h | 1 year |
| AU `QUERY_ATTRIBUTION_HISTORY` | **8 h** | 1 year (complete from mid-Aug 2024) |
| READER_ACCOUNT_USAGE `WAREHOUSE_METERING_HISTORY` | 24 h | 1 year |
| ORG `METERING_DAILY_HISTORY` / `QUERY_ATTRIBUTION_HISTORY` (premium) / `QUERY_HISTORY` (premium) | 2 h / 3 h / 3 h | 1 year / – / – |
| ORG `WAREHOUSE_METERING_HISTORY`, `RATE_SHEET_DAILY`, `CONTRACT_ITEMS` | 24 h | 1 year / indefinite |
| ORG `USAGE_IN_CURRENCY_DAILY`, `REMAINING_BALANCE_DAILY` | 72 h | indefinite; mutable to month close |
| Budgets refresh | ≤6.5 h (1 h low-latency) | monthly interval (UTC) |

Querying ACCOUNT_USAGE "uses a virtual warehouse rather than cloud services". INFORMATION_SCHEMA queries "consume only cloud services
resources". Telemetry polling by Cost CI therefore has its own cost (`INFERRED`).

## 7. Free/cheap access for an experiment
- **Trial**: the docs say it runs "for 30 days (from the sign-up date) or until you've depleted your free usage balance". No payment information is required.
  You pick the cloud, region and edition at signup ("these cannot be changed later", snowflake.com). snowflake.com says "$400 in free credits". Warehouses,
  serverless features and storage deduct from the balance (storage at the "standard On-Demand cost of a TB"). AI features are disabled until a card is added.
  Not available on trials: external network access, hybrid tables, outbound private connectivity, Openflow and Duo MFA. The $/credit used
  to draw down the $400 is not stated (`UNCONFIRMED`; presumably on-demand for the chosen edition). Choose **Enterprise** to get ACCESS_HISTORY, QAS,
  multi-cluster and Adaptive (`INFERRED` from the edition requirements above). At AWS US East on-demand prices, $400 ≈ 133 Enterprise or 200 Standard credits (`INFERRED`).
- **SNOWFLAKE_SAMPLE_DATA** (shared from `SFC_SAMPLES`; read-only; no storage charge; needs a running warehouse):
  - TPC-H schemas `TPCH_SF1` (base, "several million elements"; `lineitem` = 6,001,215 rows), `TPCH_SF10`, `TPCH_SF100` ("several hundred million")
    and `TPCH_SF1000` ("several billion"). There are 8 tables and 22 queries.
  - TPC-DS `TPCDS_SF10TCL` (10 TB; STORE_SALES ~29 billion rows) and `TPCDS_SF100TCL` (100 TB; ~300 billion rows), with 99 queries. The same page also routes TPC-DS
    access to Marketplace listings ("TPC-DS 10 TB" and "TPC-DS 10 TB Managed Iceberg"). Whether the TCL schemas are still present in every
    account is `UNCONFIRMED`.
  - If the database is missing: `CREATE DATABASE SNOWFLAKE_SAMPLE_DATA FROM SHARE SFC_SAMPLES.SAMPLE_DATA;` then `GRANT IMPORTED PRIVILEGES`.
- **Reading SNOWFLAKE.ACCOUNT_USAGE**: by default only ACCOUNTADMIN has access. There are two options:
  - `GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE r` grants all schemas. The docs warn this can expose org-level data.
  - Grant SNOWFLAKE database roles (`GRANT DATABASE ROLE SNOWFLAKE.<role> TO ROLE r`):
    - **USAGE_VIEWER** covers WAREHOUSE_METERING_HISTORY, METERING_(DAILY_)HISTORY, TASK_HISTORY, SERVERLESS_TASK_HISTORY, WAREHOUSE_LOAD/EVENTS_HISTORY,
      TABLE_QUERY_PRUNING_HISTORY and QUERY_ATTRIBUTION_HISTORY (also granted to GOVERNANCE_VIEWER).
    - **GOVERNANCE_VIEWER** covers QUERY_HISTORY, ACCESS_HISTORY, QUERY_INSIGHTS, TAG_REFERENCES and QUERY_ACCELERATION_ELIGIBLE.
    - **OBJECT_VIEWER** covers metadata views.
  - Other privileges: the IS `WAREHOUSE_METERING_HISTORY` needs `MONITOR USAGE`. `GET_QUERY_OPERATOR_STATS` needs `MONITOR` or `OPERATE` on the warehouse. The
    ORGANIZATION_USAGE billing views need `ORGANIZATION_BILLING_VIEWER` or GLOBALORGADMIN.
- **Minimum to create the experiment objects**: `CREATE WAREHOUSE` and `CREATE DATABASE` on the account. Both "Must be granted by the ACCOUNTADMIN role".
  SYSADMIN has "privileges to create warehouses and databases" by default. Warehouse-level privileges are `USAGE` (run and auto-resume), `OPERATE`
  (suspend/resume, see queries), `MODIFY` (resize) and `MONITOR`. `MANAGE WAREHOUSES` = MODIFY+MONITOR+OPERATE on all warehouses.

## 8. Documented behaviours that break naive cost estimates
1. **Minimum billing**: 60 s per start or resume. Resuming within the first minute is charged again. Interactive warehouses have a 60-minute minimum. For a short CI
   query on a cold XS, billed ≥ 0.017 credits ≫ execution_time × rate (`INFERRED`).
2. **Idle time**: the warehouse bills until auto-suspend (default 600 s, polled ~30 s). This idle time is not in any per-query figure.
   It depends on the gaps between queries in the production schedule, not on the SQL.
3. **Concurrency and queuing**: concurrent queries split credits by an undocumented weighted average. The `queued_*` times inflate elapsed
   time. `MAX_CONCURRENCY_LEVEL` (default 8) is "a default only", and small statements "count as a fraction". With multi-cluster Standard, queueing
   starts extra clusters. The marginal $ of a change depends on co-running load.
4. **Spilling**: local and then remote spill "degrades drastically" performance, and the docs' remedy is a larger warehouse. Spill is non-linear in data size (`INFERRED`).
   With QAS enabled, Snowflake "writes a small amount of data to remote storage for each eligible query, even if QAS isn't used", so
   `bytes_spilled_to_remote_storage` > 0 is not a reliable spill signal.
5. **Caching**: result-cache hits bypass execution for up to 24 h. The warehouse cache is dropped on suspend and on downsizing. CI runs can be warmer or colder than
   production.
6. **Cloud services**: per-query and per-warehouse CS credits are shown before the adjustment. Billing is an account-wide daily UTC rule. Clones, DDL, SHOW,
   INFORMATION_SCHEMA and dynamic-table change checks are CS-only. Dynamic-table checks run "on every refresh cycle, even when no data has changed".
7. **Plan estimates**: EXPLAIN `bytesAssigned` is an upper bound, and runtime (join) pruning reduces the actual scan. The plan depends on warehouse size.
8. **Background optimisation drift**: Optima Planning, Indexing and Metadata (Gen2 and Adaptive) improve repeated queries over time. QAS varies with server
   availability. Serverless tasks auto-resize from history (the first run is MEDIUM). A first CI run is not steady-state production (`INFERRED`).
9. **Warehouse-type pricing**: Gen1, Gen2, Snowpark-optimized, Interactive and Adaptive have different rates. QAS is on by default (factor 2) for new Gen2 and multi-cluster
   warehouses and adds serverless credits outside the warehouse meter.
10. **Coverage holes in attribution**: queries of about 100 ms or less are excluded. Adaptive queries appear only in QUERY_METERING_HISTORY. Cloud services and serverless costs are excluded. There is 8 h latency.
    Retries (`query_retry_time`, `fault_handling_time`) consume warehouse time. How retries are attributed is `UNCONFIRMED`.
11. **Transitions**: generation, type or constraint conversion while running double-bills until old queries finish. So does downsizing from 5XL/6XL.
12. **Dynamic tables**: DDL can trigger REINITIALIZE, a full reprocess. `EXPLAIN CHANGES` predicts the action qualitatively. The `target_lag` and `scheduler` settings drive frequency.
13. **Hybrid tables**: short hybrid-only queries do not appear in QUERY_HISTORY; use AGGREGATE_QUERY_HISTORY. Hybrid table requests are not billed from
    2026-03-01.

## 9. Open questions / UNCONFIRMED
- The exact algorithm behind `CREDITS_ATTRIBUTED_COMPUTE`: its interval length, the "resource consumption" metric, and whether Σ per query = `CREDITS_ATTRIBUTED_COMPUTE_QUERIES`.
- The Adaptive Warehouse per-query credit formula (no published rate), and the GA (docs, release note) vs "Preview" (Consumption Table footnote 5) conflict.
- The Gen2 default: CREATE WAREHOUSE and the Gen2 page say default '2', while warehouses-overview says "not the default".
- Whether QAS default-on applies to Standard Edition accounts, given that QAS is an Enterprise feature.
- Whether Snowflake strips leading comments from `QUERY_TEXT` server-side. Only dbt docs assert it.
- Whether result-cache hits need or bill a running warehouse. Whether time spent quiescing after SUSPEND is billed (implied, not stated).
- Standard multi-cluster start and stop timing thresholds (none published now). How much CS credit an EXPLAIN or compile consumes (only "does consume").
- The trial's $/credit for the $400 balance, and whether trial accounts can see ORGANIZATION_USAGE billing views (RATE_SHEET_DAILY).
- Whether TPCDS_SF10TCL and TPCDS_SF100TCL are present in SNOWFLAKE_SAMPLE_DATA for new accounts or only via Marketplace.
- The ORG `QUERY_ATTRIBUTION_HISTORY` latency (3 h) is lower than the account view's (8 h). Both are documented; the reason is unknown.

## 10. Sources
All pages were fetched 2026-09-28.
- https://docs.snowflake.com/en/sql-reference/account-usage/query_history
- https://docs.snowflake.com/en/sql-reference/functions/query_history
- https://docs.snowflake.com/en/sql-reference/account-usage/query_attribution_history
- https://docs.snowflake.com/en/sql-reference/account-usage/query_metering_history
- https://docs.snowflake.com/en/sql-reference/account-usage/warehouse_metering_history
- https://docs.snowflake.com/en/sql-reference/functions/warehouse_metering_history
- https://docs.snowflake.com/en/sql-reference/account-usage/metering_daily_history
- https://docs.snowflake.com/en/sql-reference/sql/explain
- https://docs.snowflake.com/en/sql-reference/functions/get_query_operator_stats
- https://docs.snowflake.com/en/user-guide/ui-snowsight-activity
- https://docs.snowflake.com/en/sql-reference/account-usage/query_insights
- https://docs.snowflake.com/en/user-guide/query-insights
- https://docs.snowflake.com/en/sql-reference/account-usage/table_query_pruning_history
- https://docs.snowflake.com/en/sql-reference/account-usage/access_history
- https://docs.snowflake.com/en/sql-reference/account-usage/object_dependencies
- https://docs.snowflake.com/en/sql-reference/account-usage/task_history
- https://docs.snowflake.com/en/sql-reference/account-usage/serverless_task_history
- https://docs.snowflake.com/en/sql-reference/account-usage/aggregate_query_history
- https://docs.snowflake.com/en/sql-reference/account-usage/dbt_project_execution_history
- https://docs.snowflake.com/en/sql-reference/account-usage/warehouse_load_history
- https://docs.snowflake.com/en/sql-reference/account-usage/warehouse_events_history
- https://docs.snowflake.com/en/sql-reference/account-usage/query_acceleration_history
- https://docs.snowflake.com/en/sql-reference/account-usage/query_acceleration_eligible
- https://docs.snowflake.com/en/user-guide/query-hash
- https://docs.snowflake.com/en/sql-reference/organization-usage/rate_sheet_daily
- https://docs.snowflake.com/en/sql-reference/organization-usage/usage_in_currency_daily
- https://docs.snowflake.com/en/sql-reference/organization-usage
- https://docs.snowflake.com/en/sql-reference/account-usage
- https://docs.snowflake.com/en/sql-reference/info-schema
- https://docs.snowflake.com/en/sql-reference/functions-all
- https://docs.snowflake.com/en/sql-reference/functions/system_estimate_query_acceleration
- https://docs.snowflake.com/en/sql-reference/functions/system_estimate_automatic_clustering_costs
- https://docs.snowflake.com/en/sql-reference/functions/system_estimate_search_optimization_costs
- https://docs.snowflake.com/en/user-guide/dynamic-tables/predict-refresh
- https://docs.snowflake.com/en/user-guide/dynamic-tables/cost
- https://docs.snowflake.com/en/user-guide/cost-understanding-compute
- https://docs.snowflake.com/en/user-guide/cost-understanding-overall
- https://docs.snowflake.com/en/user-guide/cost-exploring-compute
- https://docs.snowflake.com/en/user-guide/cost-attributing
- https://docs.snowflake.com/en/user-guide/cost-optimize-cloud-services
- https://docs.snowflake.com/en/user-guide/warehouses-overview
- https://docs.snowflake.com/en/user-guide/warehouses-considerations
- https://docs.snowflake.com/en/user-guide/warehouses-gen2
- https://docs.snowflake.com/en/user-guide/warehouses-multicluster
- https://docs.snowflake.com/en/user-guide/warehouses-adaptive
- https://docs.snowflake.com/en/user-guide/query-acceleration-service
- https://docs.snowflake.com/en/user-guide/snowflake-optima
- https://docs.snowflake.com/en/sql-reference/sql/create-warehouse
- https://docs.snowflake.com/en/sql-reference/sql/alter-warehouse
- https://docs.snowflake.com/en/user-guide/tasks-intro
- https://docs.snowflake.com/en/sql-reference/sql/create-clone
- https://docs.snowflake.com/en/user-guide/object-clone
- https://docs.snowflake.com/en/user-guide/data-share-consumers
- https://docs.snowflake.com/en/user-guide/data-time-travel
- https://docs.snowflake.com/en/user-guide/tables-temp-transient
- https://docs.snowflake.com/en/user-guide/querying-persisted-results
- https://docs.snowflake.com/en/sql-reference/parameters
- https://docs.snowflake.com/en/user-guide/performance-query-warehouse-cache
- https://docs.snowflake.com/en/user-guide/performance-query-warehouse-memory
- https://docs.snowflake.com/en/user-guide/object-tagging/introduction
- https://docs.snowflake.com/en/user-guide/resource-monitors
- https://docs.snowflake.com/en/user-guide/budgets
- https://docs.snowflake.com/en/user-guide/cost-anomalies
- https://docs.snowflake.com/en/user-guide/admin-trial-account
- https://docs.snowflake.com/en/user-guide/sample-data
- https://docs.snowflake.com/en/user-guide/sample-data-using
- https://docs.snowflake.com/en/user-guide/sample-data-tpch
- https://docs.snowflake.com/en/user-guide/sample-data-tpcds
- https://docs.snowflake.com/en/sql-reference/snowflake-db-roles
- https://docs.snowflake.com/en/user-guide/security-access-control-privileges
- https://docs.snowflake.com/en/user-guide/security-access-control-overview
- https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-api
- https://docs.snowflake.com/en/release-notes/new-features-2026
- https://docs.snowflake.com/en/release-notes/2026/other/2026-06-16-adaptive-compute-ga
- https://docs.snowflake.com/en/release-notes/2026/other/2026-09-15-dynamic-tables-predict-refresh
- https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf (Snowflake Service Consumption Table, effective 2026-09-25)
- https://www.snowflake.com/en/snowflake-trial/
- https://docs.getdbt.com/reference/resource-configs/snowflake-configs
- https://docs.getdbt.com/reference/project-configs/query-comment
