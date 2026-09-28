# Databricks: primary-source research for Cost CI

Researched 2026-09-28 against live official docs: docs.databricks.com (AWS and GCP editions), learn.microsoft.com/azure/databricks (pages dated 2026-09-11 to 2026-09-16), databricks.com/product/pricing, and docs.getdbt.com. Doc wording is paraphrased. Identifiers and numbers are exact.
Classification legend: **DIRECTLY_MEASURED** means Databricks records the value. **DERIVED** means a deterministic computation from recorded data plus documented constants. **ESTIMATED** means it needs a model, an apportionment rule or an external price. **UNAVAILABLE** means it is not exposed. **UNCONFIRMED** means it could not be verified from a primary source.

## 1. Summary

- **DBUs are recorded natively; dollars only at list price.** `system.billing.usage` records DBUs per SKU × resource × hour window. It is global, typically available within 12 hours, and kept 365 days. `system.billing.list_prices` holds published list prices only. Negotiated or committed discounts appear in no system table, budget, or Governance Hub cost view.
- **Per-job-run DBUs are native for job compute and serverless jobs** (`usage_metadata.job_run_id`). They are not native for jobs on all-purpose compute or SQL warehouses; the docs say all-purpose attribution cannot be exact.
- **Per-query cost on SQL warehouses is not native.** Billing stops at `warehouse_id` × hour. `system.query.history` (GA 2026-09-21, typically ≤1 h, 365 d, regional) gives per-statement time, bytes, cache flags, `query_source` and `query_tags`. Splitting warehouse cost across queries is up to Cost CI.
- **`system.query.history` coverage is limited.** It covers SQL warehouses, serverless notebooks/jobs and Lakeflow pipelines only. Spark or SQL on classic all-purpose/job clusters has no statement-level system table.
- **Cloud VM, disk and network cost for classic compute is outside Databricks.** The cloud provider bills it and it is absent from system tables. Serverless DBU prices include the VM. VM-seconds by instance and spot status can be DERIVED from `system.compute.instance_events` (Public Preview).
- **No pre-execution cost estimate exists.** `EXPLAIN COST` shows only optimizer statistics (`sizeInBytes`, `rowCount`) when available. Databricks' serverless FAQ tells users to benchmark a representative workload and read the billing table.
- **CI building blocks are good, except caching.** Unity Catalog shallow clones and time travel; `SET use_cached_result = false`; `samples.tpcds_sf1` / `tpcds_sf1000` / `tpch`; tagged dedicated warehouses; the Query History API (`GET /api/2.0/sql/history/queries`, filterable by `statement_ids`, returns RUNNING queries). The disk cache cannot be turned off on SQL warehouses or serverless.
- **dbt join key and dbt MV/ST billing.** dbt-databricks ≥1.11 auto-tags every query `@@dbt_model_name` / `@@dbt_materialized` (SQL warehouses only). dbt materialized views and streaming tables are billed as serverless pipelines, not to the warehouse.

## 2. Primitive table

| # | Primitive | Object / API (exact names) | Granularity | Latency & retention | Class. | Conditions for converting to $ | Source |
|---|---|---|---|---|---|---|---|
| 1 | Billable usage (DBU) | `system.billing.usage`: `record_id`, `account_id`, `workspace_id`, `sku_name`, `cloud`, `usage_start_time`, `usage_end_time`, `usage_date`, `usage_unit` (e.g. `DBU`), `usage_quantity`, `usage_type` (`COMPUTE_TIME`,`STORAGE_SPACE`,`NETWORK_BYTE`,`NETWORK_HOUR`,`API_OPERATION`,`TOKEN`,`GPU_TIME`,`ANSWER`), `record_type` (`ORIGINAL`/`RETRACTION`/`RESTATEMENT`), `ingestion_date`, `billing_origin_product`, `custom_tags`, `usage_metadata`, `identity_metadata`, `product_features` | Hour windows: the doc example is 10:00→11:00 UTC and the correction query is called "hourly usage". Rows are per SKU × resource. Serverless can emit several rows per workload per window; the docs say to sum them. Classic driver and worker are one row if they use the same instance type. | ORIGINAL rows typically ≤12 h (longer for new workspaces). Corrections arrive later. Serverless FAQ: up to 24 h. 365 d (configurable, see §6). Global; streamable. | DIRECTLY_MEASURED (DBU) | Join `list_prices` on `cloud`, `sku_name` and the price time window. SUM across record types so retractions net out. Result is list price only. | [1][2][3][6][40] |
| 2 | Attribution keys | `usage_metadata.cluster_id` (non-serverless: notebooks, jobs, pipelines)<br>`.job_id`, `.job_run_id` (serverless jobs and job compute; never all-purpose)<br>`.warehouse_id`<br>`.notebook_id`, `.notebook_path` (serverless notebooks)<br>`.dlt_pipeline_id`, `.dlt_update_id`, `.dlt_maintenance_id` (pipelines, MVs, online tables, Lakeflow Connect)<br>`.instance_pool_id`<br>`.node_type` (no driver/worker split; set for all SQL warehouses)<br>`.job_name`<br>`.usage_policy_id` (`budget_policy_id` is deprecated)<br>`.uc_table_catalog`, `.uc_table_schema`, `.uc_table_name` (MVs)<br>`.metastore_id` (null on Azure/GCP), `.catalog_id` (default storage, Azure page)<br>`.endpoint_id`, `.app_id`, `.base_environment_id`, … | per usage row | same as #1 | DIRECTLY_MEASURED | n/a | [1][2][3] |
| 3 | Identity & product features | `identity_metadata.run_as` (all-purpose compute = cluster creator; serverless notebook = session creator, including shared-session use), `.owned_by` (SQL warehouses only), `.created_by`<br>`product_features.jobs_tier` (`LIGHT`/`CLASSIC`), `.sql_tier` (`CLASSIC`/`PRO`), `.dlt_tier` (`CORE`/`PRO`/`ADVANCED`), `.is_serverless` (null when there is no classic alternative), `.is_photon`, `.performance_target` (`PERFORMANCE_OPTIMIZED`/`STANDARD`; null when non-serverless), `.networking.connectivity_type` | per usage row | same as #1 | DIRECTLY_MEASURED | Tier and Photon choose the SKU and therefore the price | [1][2] |
| 4 | Custom tags on usage | `system.billing.usage.custom_tags` (map) holds workspace, cluster, pool and warehouse tags, plus serverless usage-policy tags. MV/ST refreshes inherit the SQL warehouse's tags (since 2026-08-03). | per usage row | Workspace tags take up to 1 h to propagate; cluster tag edits apply after restart | DIRECTLY_MEASURED | n/a | [1][53][56][86] |
| 5 | List prices | `system.billing.list_prices`: `price_start_time`, `price_end_time`, `account_id`, `sku_name`, `cloud`, `currency_code`, `usage_unit`, `pricing` struct. Example: `{"default":"0.10","promotional":{"default":"0.07"},"effective_list":{"default":"0.07"}}`. Keys: `default` = single price for simple long-term estimates; `promotional` = temporary price all customers get; `effective_list` = list price used for cost. | One row per SKU price change | Retained indefinitely; global | DIRECTLY_MEASURED (published list) | Look up the latest `price_start_time` ≤ usage time. Docs samples use either `pricing.default` or `pricing.effective_list.default`. | [4][6][11] |
| 6 | Negotiated / effective price | None in system tables. Budgets ignore credits and negotiated discounts. The Governance Hub Cost page (Beta) shows list price only. Usage dashboards let admins hand-edit $/DBU per SKU. | n/a | n/a | UNAVAILABLE | Cost CI must take the discount per SKU as configuration | [63][64][65] |
| 7 | Per-job-run DBU cost | `billing_origin_product='JOBS'` rows keyed by `usage_metadata.job_id` / `job_run_id`. The docs provide a CTE `list_cost_per_job_run`. | job run × hour × SKU | as #1 | DIRECTLY_MEASURED (DBU). Classic VM cost is excluded. | List price; add cloud VM/disk/network for classic from the cloud bill | [11][9] |
| 8 | Job cost on all-purpose compute, SQL warehouse, or `WORKFLOW_RUN` | No `job_id`/`job_run_id` in billing. Jobs on warehouses or all-purpose compute are not billed as jobs. `WORKFLOW_RUN` usage is charged to the parent notebook. | cluster or warehouse × hour | as #1 | UNAVAILABLE natively; ESTIMATED by apportionment | Time-share or task-time model; docs say estimates are approximate | [9][10][11] |
| 9 | Per-query cost on a SQL warehouse | No native field. Billing granularity ends at `warehouse_id` × hour. The docs' warehouse-cost example aggregates by day and SKU. | n/a | n/a | UNAVAILABLE → ESTIMATED | Apportion warehouse-hour DBUs by, e.g., share of `total_task_duration_ms`. Idle, startup and scale-out time must be allocated by policy. | [29][5] |
| 10 | Statement metrics | `system.query.history` columns:<br>• IDs & compute: `statement_id`, `session_id`, `execution_status`, `compute` struct (`type` = `WAREHOUSE`/`SERVERLESS_COMPUTE`/`CLASSIC_COMPUTE`; `warehouse_id` only for WAREHOUSE; `cluster_id` never populated)<br>• Durations: `total_duration_ms`, `waiting_for_compute_duration_ms`, `waiting_at_capacity_duration_ms`, `compilation_duration_ms`, `execution_duration_ms`, `total_task_duration_ms`, `result_fetch_duration_ms`<br>• Scan: `read_partitions`, `pruned_files`, `pruned_files_bytes`, `read_files`, `read_files_bytes`, `read_rows`, `read_bytes`<br>• Output & shuffle: `produced_rows`, `spilled_local_bytes`, `written_bytes`, `written_rows`, `written_files`, `shuffle_read_bytes`<br>• Cache: `read_io_cache_percent`, `from_result_cache`, `cache_origin_statement_id`<br>• Other: `statement_type`, `client_application`, `client_driver`, `executed_by`, `executed_as`, `statement_text` | per statement | Typically ≤1 h (the CMK case is excluded from this). 365 d. Regional: only workspaces in the reader's region. Not streamable. | DIRECTLY_MEASURED (resources, not $) | Needs an apportionment model (#9). `statement_text` shows `<REDACTED>` unless the reader is admin or in `databricks_pii_access` (since 2026-08-26). | [5][86] |
| 11 | Statement → workload links | `query_source`: `job_info{job_id, job_run_id, job_task_run_id}`, `notebook_id`, `dashboard_id`, `legacy_dashboard_id`, `alert_id`, `sql_query_id`, `genie_space_id`. `query_parameters`. `query_tags` (map; SQL warehouses only; Public Preview). | per statement | as #10 | DIRECTLY_MEASURED | Join to billing via `job_run_id`, `notebook_id` or `warehouse_id` + hour | [5][22] |
| 12 | Query History API | `GET /api/2.0/sql/history/queries`. Filters: `filter_by.query_start_time_range` (≤30 days per request), `statuses` (QUEUED, RUNNING, CANCELED, FAILED, FINISHED), `user_ids`, `warehouse_ids`, `statement_ids`. Params: `include_metrics` (docs: use only for small result sets), `max_results` (<1000, default 100). Returns `query_tags`, `query_source`, `statement_type`, `channel_used`, `plans_state`.<br>Metrics:<br>• Time: `total_time_ms`, `compilation_time_ms`, `execution_time_ms`, `task_total_time_ms`, `photon_total_time_ms`, `result_fetch_time_ms`<br>• I/O: `read_bytes`, `read_remote_bytes`, `read_cache_bytes`, `read_files_bytes`, `write_remote_bytes`, `spill_to_disk_bytes`, `network_sent_bytes`<br>• Rows & files: `rows_read_count`, `rows_produced_count`, `read_files_count`, `read_partitions_count`, `pruned_bytes`, `pruned_files_count`, `result_from_cache`<br>• Queue & progress: `provisioning_queue_start_timestamp`, `overloading_queue_start_timestamp`, `query_compilation_start_timestamp`, `projected_remaining_task_total_time_ms`, `remaining_task_count` | per query | Latency not documented. It returns RUNNING/QUEUED queries, so it is near-real-time (DERIVED). Retention UNCONFIRMED. | DIRECTLY_MEASURED | as #10; adds Photon time | [17][18][19] |
| 13 | Query profile | UI for SQL warehouses and serverless compute. Shows per-operator time, rows and peak memory, plus aggregated task time and I/O. Downloadable as JSON. Not available for result-cache hits. | query / operator | n/a | DIRECTLY_MEASURED (UI/JSON). A programmatic full-profile API is UNCONFIRMED. | n/a | [21] |
| 14 | Warehouse configuration | `system.compute.warehouses` (SCD snapshots): `warehouse_id`, `warehouse_name`, `warehouse_type` (`CLASSIC`/`PRO`/`SERVERLESS`), `warehouse_channel` (`CURRENT`/`PREVIEW`), `warehouse_size` (`2X_SMALL` … `5X_LARGE`), `min_clusters`, `max_clusters`, `auto_stop_minutes`, `tags`, `change_time`, `delete_time` | per change | Latency not documented; 365 d | DIRECTLY_MEASURED | Size → DBU/h (§3; documented for serverless on Azure) | [14][6] |
| 15 | Warehouse lifecycle | `system.compute.warehouse_events`: `warehouse_id`, `event_type` (`STARTING`,`RUNNING`,`SCALED_UP`,`SCALED_DOWN`,`STOPPING`,`STOPPED`), `cluster_count`, `event_time` | per event | Latency not documented; 365 d; streamable | DERIVED (uptime × clusters) | × DBU/h(size) × list price. Reconcile against #1. | [15] |
| 16 | Classic cluster configuration | `system.compute.clusters`:<br>• Identity: `cluster_id`, `cluster_name`, `owned_by`, `cluster_source` (`UI`/`API` = all-purpose; `JOB`; `PIPELINE`; `PIPELINE_MAINTENANCE`)<br>• Sizing: `driver_node_type`, `worker_node_type`, `worker_count`, `min_autoscale_workers`, `max_autoscale_workers`, `auto_termination_minutes`, `enable_elastic_disk`<br>• Runtime & policy: `dbr_version`, `data_security_mode`, `policy_id`, `tags`<br>• Cloud: `aws_attributes.availability` / `.first_on_demand` / `.spot_bid_price_percent`, `azure_attributes`, `gcp_attributes`<br>• Timestamps: `create_time`, `change_time`, `delete_time` | per change | Latency not documented; 365 d. Classic all-purpose and job compute only. | DIRECTLY_MEASURED | n/a | [12] |
| 17 | Node utilization | `system.compute.node_timeline` (one row per instance-minute): `instance_id`, `cluster_id`, `driver`, `node_type`, `start_time`, `end_time`, `cpu_user_percent`, `cpu_system_percent`, `cpu_wait_percent`, `mem_used_percent`, `mem_swap_percent`, `network_sent_bytes`, `network_received_bytes`, `disk_free_bytes_per_mount_point`. Also `system.compute.node_types`: `core_count`, `memory_mb`, `gpu_count`. | 1 minute | Latency not documented. 90 d. Nodes that ran under 10 min may be missing. No serverless or warehouses. | DIRECTLY_MEASURED | VM-minutes × cloud price (external) → ESTIMATED | [12][6] |
| 18 | Instance lifecycle | `system.compute.instance_events` (Public Preview, 2026-05-21): `instance_id`, `event_type` (`INSTANCE_LAUNCHING`/`STATE_TRANSITION`), `state` (`INSTANCE_LAUNCHING`,`INSTANCE_READY`,`INSTANCE_PLACED`,`INSTANCE_TERMINATED`), `cluster_id` (only when PLACED), `instance_pool_id`, `node_type`, `availability_type` (`ON_DEMAND`/`SPOT`; `PREEMPTIBLE` on GCP). Also `system.compute.instance_pools`. | per state change | Latency not documented; 365 d | DERIVED (VM-seconds, including idle pool and launch time; docs give an idle/active SQL) | × cloud on-demand/spot price → ESTIMATED | [12][89] |
| 19 | Jobs & runs | `system.lakeflow.jobs`, `job_tasks` (SCD2)<br>`job_run_timeline`: `run_id`, `run_type` (`JOB_RUN`/`SUBMIT_RUN`/`WORKFLOW_RUN`), `period_start_time`, `period_end_time`, `compute_ids`, `compute`, `result_state`, `termination_code`, `job_parameters`; `*_duration_seconds` (legacy single-task only)<br>`job_task_run_timeline`: `run_id` (task run), `job_run_id`, `task_key`, `compute_ids` (job clusters, interactive clusters, SQL warehouses), `setup_duration_seconds`, `execution_duration_seconds`, `cleanup_duration_seconds` | run or task × ≤1 h slice (clock-hour aligned since 2026-01-19) | Typically ≤1 h after `period_end_time`. 365 d; the latest SCD2 row is kept indefinitely. Regional. | DIRECTLY_MEASURED | Join billing on `workspace_id`, `job_id`, `job_run_id` | [9][10] |
| 20 | Pipelines / MV / ST updates | `system.lakeflow.pipelines`; `system.lakeflow.pipeline_update_timeline` (Preview): `update_id`, `update_type`, `trigger_type`, `compute`, `refresh_selection`, `full_refresh_selection`, hourly slices. Billing: `dlt_pipeline_id` / `dlt_update_id`. DBSQL MVs appear as `billing_origin_product='SQL'` with `dlt_pipeline_id` NOT NULL and `uc_table_*` set. | update × hour | 365 d; latency UNCONFIRMED | DIRECTLY_MEASURED | List price | [10][61][62][2] |
| 21 | Lineage | `system.access.table_lineage` / `column_lineage`: `entity_type` (`NOTEBOOK`,`JOB`,`PIPELINE`,`DASHBOARD_V3`,`DBSQL_DASHBOARD`,`DBSQL_QUERY`), `entity_id`, `entity_run_id`, `entity_metadata{job_info{job_id,job_run_id}, dlt_pipeline_info, notebook_id, sql_query_id, dashboard_id, genie_space_id, alert_id}`, `source_table_full_name`, `target_table_full_name`, `source_path`, `target_path`, `source_type`, `target_type`, `statement_id` (set only for SQL-warehouse queries), `event_time`, `created_by` | per read/write event (best effort; only events where lineage can be inferred) | Latency not documented; rolling 365 d | DIRECTLY_MEASURED (a subset of events) | Maps tables to the workloads that read/write them (impact set for a PR) | [16] |
| 22 | Predictive optimization | `system.storage.predictive_optimization_operations_history`: `catalog_name`, `schema_name`, `table_name`, `operation_type` (COMPACTION, VACUUM, ANALYZE, CLUSTERING, …), `operation_status`, `operation_metrics`, `usage_unit`=`ESTIMATED_DBU`, `usage_quantity`, `start_time`, `end_time` | per operation per table | ≤2 h (billing up to 24 h); 180 d | ESTIMATED (per-operation DBUs approximated; cluster total accurate) | List price of the PO SKU | [16b] |
| 23 | Plan-time estimates | `EXPLAIN [EXTENDED\|CODEGEN\|COST\|FORMATTED]`. `COST` prints the logical plan plus `Statistics(sizeInBytes=…, rowCount=…)` when statistics exist; DBR 16.0+ lists tables with missing/partial/full stats. `ANALYZE TABLE … COMPUTE STATISTICS` collects row count, size and column stats; PO runs it automatically on UC managed tables. | per plan node | pre-execution | ESTIMATED (no DBU or $) | Requires a bytes/rows → DBU model calibrated on #10 | [24][25][26] |
| 24 | Storage footprint | `DESCRIBE DETAIL` (`sizeInBytes` and `numFiles` of the latest snapshot); `ANALYZE TABLE … COMPUTE STORAGE METRICS` (`total_bytes`, `active_bytes`, `vacuumable_bytes`, `time_travel_bytes`, `num_*_files`; DBR 18.0+); `DESCRIBE HISTORY` `operationMetrics` (e.g. `numAddedBytes`, `numRemovedBytes`) | per table / commit | on demand | DIRECTLY_MEASURED (bytes) | × cloud storage price (external), or DSU for default storage → ESTIMATED | [28][27][73] |
| 25 | Default storage (serverless workspaces) | Billing rows with `billing_origin_product='DEFAULT_STORAGE'` and `usage_type` `STORAGE_SPACE`/`API_OPERATION`, measured in DSU; `usage_metadata.storage_api_type` (`TIER_1` = PUT/COPY/POST/LIST; `TIER_2` = other) | metastore (Azure page also lists `catalog_id`) | as #1 | DIRECTLY_MEASURED | List price; cloud-provider credits and discounts do not apply | [67][2] |
| 26 | Cloud VM / disk / network (classic) | Not in any documented system table; billed by the cloud provider. Default tags (`ClusterId`, `JobId`, `RunName`, `SqlEndpointId`, `Creator`, `Vendor`) propagate to AWS EC2/EBS, Azure VMs (managed resource group) and GCP GCE labels. `system.billing.cloud_infra_cost` appears only in non-primary sources → UNCONFIRMED. | cloud billing | cloud provider | UNAVAILABLE in Databricks (measured in the cloud bill) | Join cloud cost exports on those tags | [53][54][55][49][37] |

## 3. Billing rules

- **DBU definition.** A DBU is a normalized unit of processing power ([37]), expressed as processing capability per hour and set by VM instance type ([50]).
- **Billing granularity.** Pay-as-you-go has no upfront cost and is billed at per-second granularity ([37]).
- **Minimum billing increments and startup billing are UNCONFIRMED.** It was not found whether cluster or warehouse startup is billed, or whether a minimum increment applies.
- **Classic compute total cost.** Classic total cost = DBUs + cloud VM + disk + network, billed by the cloud provider for resources in the customer account. For serverless, the DBU price already includes the VM ([49][37]).
- **Where compute runs.** Classic compute runs in the customer's cloud account; serverless runs in the Databricks account ([51][33]). On Azure, running clusters add VMs, disks, IPs and NICs to the workspace's managed resource group ([52]).
- **SKU families**, visible through `billing_origin_product` and `product_features` ([1][2]):
  - `JOBS`: Jobs Compute, `jobs_tier` CLASSIC/LIGHT.
  - `ALL_PURPOSE`.
  - `SQL`: `sql_tier` CLASSIC/PRO, plus SQL Serverless, plus DBSQL MV/ST refreshes.
  - `DLT`: `dlt_tier` CORE/PRO/ADVANCED; Core = streaming ingest, Pro = +CDC, Advanced = +expectations ([60]).
  - `INTERACTIVE`: serverless notebooks.
  - Also `PREDICTIVE_OPTIMIZATION`, `DEFAULT_STORAGE` and `NETWORKING`, among others.
  - Some products share a SKU. For example, data quality monitoring, predictive optimization and serverless workflows all bill under the serverless jobs SKU ([2]).
- **Serverless SKU multipliers (Azure page, [36]).** The bill and system tables show DBUs after the multiplier.
  - Automated Serverless SKU: Serverless Jobs 1X, Serverless Spark Declarative Pipelines 1X, Predictive Optimization 1X, Data Quality Monitoring 2X, Fine-Grained Access Control 1X, MV/ST in Databricks SQL 1X, Data Classification 3X.
  - Interactive Serverless SKU: Serverless Notebook 1X.
- **SQL Serverless DBU/hour per warehouse cluster size ([36], Azure).**
  - 2X-Small 4, X-Small 6, Small 12, Medium 24, Large 40, X-Large 80, 2X-Large 144, 3X-Large 272, 4X-Large 528.
  - 5X-Large is not listed. Its status is Beta or Public Preview; the docs are inconsistent ([14][30][91]).
  - The AWS and GCP URLs for this page redirect to the dynamic pricing page, so the AWS/GCP DBU/h are UNCONFIRMED. Classic/Pro DBU/h are UNCONFIRMED.
  - Azure says serverless may use different instance types than classic/pro but has similar price/performance ([31]).
- **Warehouse hardware (classic/pro).**
  - AWS: 2X-Small = i3.2xlarge driver + 1 worker … 4X-Large = i3.16xlarge + 256 workers; 5X-Large = 512 workers ([30]).
  - Azure: every worker is Standard_E8ds_v4, and each node has a 256 GB Premium SSD that Azure bills hourly ([31]).
  - GCP: every worker is n2-highmem-8; 2X-Small = 16 vCPU … 4X-Large = 2112 vCPU ([32]).
- **Warehouse behaviour.**
  - UI default size is X-Large; default min = max = 1 cluster ([35]).
  - Classic/pro allow at most one cluster per 10 concurrent queries.
  - Classic/pro autoscaling adds clusters based on the estimated time to clear running + queued work: 2–6 min → +1, 6–12 → +2, 12–22 → +3, then +1 per extra 15 min. A query waiting 5 min in queue triggers scale-up; 15 min of low load triggers scale-down ([30][31]).
  - Serverless uses Intelligent Workload Management instead (ML-predicted admission and fast scale up/down). Every type has a 1,000-query queue cap.
  - Startup: serverless 2–6 s; pro/classic about 4 min ([33]).
  - Clusters are recycled about every 24 h ([35][31]).
- **Auto-stop.** Serverless defaults to 10 min, with a minimum of 5 in the UI and 1 via API. Pro/classic default to 45 min, minimum 10. Idle warehouses keep accruing DBU and cloud-instance charges until they stop ([35]).
- **Classic autoscaling ([45]).**
  - Optimized autoscaling applies on Premium plan and above. It goes min→max in at most 2 steps and scales down by a percentage of nodes. Job compute scales down after 40 s of underutilization; all-purpose after 150 s.
  - Standard autoscaling starts by adding 8 nodes, then grows exponentially. It scales down when 90% of nodes are not busy for 10 min and the compute has been idle for at least 30 s.
  - Auto-termination can be set from 10 to 10,000 min. Idle compute accrues DBU + cloud charges until it terminates ([46]).
  - A new job compute cluster terminates when its job finishes ([46]).
  - Pool instances incur no DBUs while idle in the pool, but the cloud provider still bills them ([49]).
- **Spot instances.** The driver (first instance) is always on-demand; subsequent instances are spot ([45]). Whether the DBU rate is the same for spot and on-demand is UNCONFIRMED; only the VM price differs in cloud billing.
- **Serverless jobs performance mode ([39]).**
  - Standard mode uses less compute and fewer DBUs on the same SKU, with 4–6 min startup latency. Performance-optimized mode starts and runs faster.
  - Recorded in `product_features.performance_target`.
  - Timeline: Standard for one-time runs via the Jobs API (2026-09-11, [85]). MVs support standard mode (2026-07-06, [87]). dbt-task performance mode propagates to MV/ST refreshes, trading <1 min for 4–6 min startup (2026-08-20, [86]).
- **Serverless limits.** Maximum runtime is 7 days ([42]). The default notebook execution timeout is 2.5 h / 9,000 s ([41]).
- **Photon ([44]).**
  - Always on for serverless, SQL warehouses and serverless pipelines.
  - On by default for classic compute created in the UI. The Clusters/Jobs API requires `runtime_engine=PHOTON`.
  - Photon instance types consume DBUs at a different rate; Azure says Photon increases the DBU count ([69]).
  - The numeric multiplier lives on the dynamic instance-types pricing page → UNCONFIRMED.
- **Committed use vs PAYG.**
  - Committing to usage levels unlocks discounts ([37]).
  - Azure DBCU prepurchase runs 1 or 3 years and draws down at list-price ratios. Example: All-purpose Premium 0.55 DBCU per DBU, Jobs Premium 0.30. It covers DBUs only; compute, storage and networking bill separately; no cancel or exchange ([69]).
- **Where the effective price is visible.** None of Databricks' cost surfaces show it: system tables, budgets and the Governance Hub cost page all use list price ([4][64][65]).
  - Usage dashboards accept manual per-SKU $/DBU overrides ([63]).
  - On Azure, actual charges appear in Azure Cost Management with Databricks tags ([49]). The discount appearing there is DERIVED, not stated.
  - On AWS/GCP, the invoice or contract is the only source (UNCONFIRMED in docs).
- **Free trial ([83][84]).**
  - Credits are valid 14 days, up to $400.
  - Personal-email trials cap serverless compute at 50 DBU/h and allow one SQL warehouse capped at 50 DBU/h.
  - After the trial the account becomes pay-as-you-go.

## 4. CI / isolation primitives

- **Shallow clone** (`CREATE TABLE t SHALLOW CLONE src [VERSION AS OF n | TIMESTAMP AS OF ts]`, available in Databricks SQL and DBR) ([70][72]).
  - Copies only metadata and points at the source's data files.
  - Cheaper than deep clone in both compute and storage.
  - Changes to the clone never affect the source. The clone has its own history, so time-travel versions differ from the source's.
  - Docs recommend shallow clones for testing a workflow against a production table without corrupting it.
  - The command returns `source_table_size`, `source_num_of_files`, `num_removed_files`, `num_copied_files`, `removed_files_size`, `copied_files_size`.
  - Not copied: table description, commit metadata, history, UC tags.
- **Unity Catalog clone constraints ([71][72]).**
  - DBR 13.3 LTS+ for managed tables; 14.3 LTS+ for external.
  - Managed clones only to managed, external only to external.
  - No shallow clone of a shallow clone. No `CREATE OR REPLACE` over an existing UC shallow clone: drop it and recreate, or use a new name. Shallow clones cannot be shared via OpenSharing.
  - Delta only. Managed Iceberg supports deep clone only. MVs and streaming tables do not support `CLONE`.
  - For managed tables, `VACUUM` on either the source or the target might delete the source's files. For external tables, only VACUUM on the source does.
  - A dropped base table still serves its clones until its files are purged after the 7-day `UNDROP` window.
  - Required privileges: `USE CATALOG`/`USE SCHEMA` on the source, and `USE SCHEMA` + `CREATE TABLE` on the target.
- **Deep clone** is the default when no type is given. It copies data and metadata (including stream and `COPY INTO` metadata). Re-cloning is incremental: it commits only what changed since the last clone. It is expensive because it copies data ([70][72]).
- **Time travel** ([73]).
  - Syntax: `VERSION AS OF`, `TIMESTAMP AS OF`, `t@v123`.
  - Defaults: `delta.logRetentionDuration` = 30 days; `delta.deletedFileRetentionDuration` = 7 days. In DBR 18.0+, log retention must be ≥ deleted-file retention.
  - VACUUM removes the files older versions need. Longer retention raises storage cost.
  - Pinning a CI input to a version gives reproducible benchmarks.
- **Result cache.** Local (per-cluster, in memory) and remote (serverless only, persisted) result caches last 24 h and are invalidated when underlying tables change. The UI cache lasts ≤7 days ([74]).
  - `SET use_cached_result = false` turns off reuse; docs reserve it for testing and benchmarking ([74][75]).
  - Result-cache hits appear as `from_result_cache` / `cache_origin_statement_id` and have no query profile ([5][21]).
- **Disk (IO) cache** is controlled by the Spark conf `spark.databricks.io.cache.enabled` ([77]).
  - Databricks SQL supports only 7 parameters: ANSI_MODE, LEGACY_TIME_PARSER_POLICY, MAX_FILE_PARTITION_BYTES, READ_ONLY_EXTERNAL_METASTORE, STATEMENT_TIMEOUT, TIMEZONE, USE_CACHED_RESULT ([76]).
  - Serverless notebooks/jobs allow only 6 Spark confs, and the IO cache is not among them ([43]).
  - Therefore the disk cache cannot be disabled on warehouses or serverless (DERIVED from [76][43]). `CACHE SELECT` is ignored on SQL warehouses ([77]). `df.cache()` / `CACHE TABLE` raise errors on serverless ([42]).
  - Warmth has to be measured, not controlled: `read_io_cache_percent`, `read_cache_bytes`.
- **Job clusters per run** ([58]).
  - A single-task cluster starts when the task run begins and terminates after it.
  - A shared job cluster lives from the first to the last task that uses it.
  - Serverless is the default for every task that supports it. All-purpose compute is not recommended for production jobs.
  - A dbt task runs the dbt CLI on serverless or single-node job compute, and the SQL it generates on the chosen SQL warehouse ([59]).
- **Dedicated CI warehouse (design option, DERIVED).**
  - A tagged serverless warehouse used only by CI gives a clean `usage_metadata.warehouse_id` series. Setting auto-stop to 1 min via API minimizes idle tail ([35]).
  - Use `warehouse_events` for fast uptime × DBU/h, then reconcile with billing about 12–24 h later.
  - `STATEMENT_TIMEOUT` and the warehouse-level `statement_timeout` (Beta) bound CI spend ([76][31]).
- **Sample datasets.** These are read-only in the `samples` catalog ([78][79][80]).
  - `samples.tpcds_sf1` (~1 GB) and `samples.tpcds_sf1000` (~1 TB) are present by default in every UC-enabled workspace.
  - `samples.tpch` is described as ~1 TB on the samples page. Row counts and scale factor are not stated → verify with `DESCRIBE DETAIL`.
  - `samples.nyctaxi.trips` (size undocumented); `samples.wanderbricks`; `samples.databricks` (`/Volumes/samples/databricks/datasets/`).
  - `/databricks-datasets` on DBFS may change without notice.
- **Free Edition ([81][82]).**
  - Serverless-only and quota-limited, with a daily fair-use cap: exceeding it shuts compute down for the rest of the day, sometimes the month.
  - One 2X-Small SQL warehouse; at most 5 concurrent job tasks; one active pipeline per type.
  - No classic compute, no account console and no account-level APIs.
  - Non-commercial use only; no SLA.
  - Availability of system tables and `samples` is UNCONFIRMED.

## 5. Attribution primitives

- **Custom tags.**
  - Taggable objects: workspaces, pools, all-purpose and job compute, SQL warehouses, database instances, Lakebase projects ([53][54]).
  - Tags reach `custom_tags` in billing and the cloud resources: AWS EC2/EBS, Azure VMs, GCP GCE labels.
  - Default tags: `Vendor`, `ClusterId`, `ClusterName`, `Creator`. Job compute adds `RunName` and `JobId`. Warehouses carry `SqlEndpointId`, and on Azure also `ClusterId`. Pools carry `DatabricksInstancePoolId` and `DatabricksInstancePoolCreatorId`.
  - Pool-created VMs get only workspace + pool tags (AWS: cluster tags still reach DBU usage).
  - On Azure, a custom tag that collides with a default tag is renamed with an `x_` prefix.
- **Tag limits.**
  - AWS: 20 tags per workspace resource, with a restricted character set.
  - Azure: 50 tags per Azure resource.
  - GCP: 54 labels, 63 chars, lowercase; `@` becomes `_at_`; propagation can lag GCE API rate limits ([55]).
  - Workspace tag changes take up to 1 h; cluster tag changes apply only after restart.
  - Legacy DBU usage reports exclude serverless.
- **Job tags** propagate to the job clusters a run creates ([57]). Whether job tags reach `custom_tags` for **serverless** jobs is UNCONFIRMED; the documented path is serverless usage policies.
- **Serverless usage policies** (Public Preview; formerly budget policies) ([56]).
  - Policy tags land in `custom_tags` and `usage_metadata.usage_policy_id`, for notebooks, jobs, pipelines, serving endpoints, Apps and Lakebase.
  - They do not tag classic compute.
  - Existing assets are not auto-assigned. Policy changes affect only future usage. Pipelines triggered by a job do not inherit the job's policy. With no explicit choice, the alphabetically first policy is used.
- **Pipelines and materialized views.**
  - Pipeline tags are not tied to billing ([60]).
  - DBSQL MV/ST refreshes run on a serverless pipeline that Databricks creates automatically. The warehouse only coordinates. They bill as serverless-pipeline DBUs even when the warehouse is pro or classic ([61]).
  - Since 2026-08-03 these refreshes inherit the warehouse's custom tags ([86]).
- **Query tags** (Public Preview; Databricks SQL workloads only; `query_tags` is null for other compute) ([22][23]).
  - Session-level: set via the connection parameter `query_tags` (`key:value,…`; Simba drivers use `ssp_query_tags`) or `SET QUERY_TAGS['k']='v'`.
  - Statement-level: via the Python (≥4.2.6), Node.js (≥1.12.0) and Go (≥1.9.0) connectors, and the Statement Execution API.
  - Limits: 20 user tags, 128-char values, 10 KB per session. Keys may not contain `, : - / = .`.
  - Tags appear in `system.query.history.query_tags`, the Query History UI and the List Queries API. They do **not** appear in `system.billing.usage`.
- **dbt-databricks ([94]).**
  - v1.11+ adds reserved tags `@@dbt_model_name`, `@@dbt_core_version`, `@@dbt_databricks_version`, `@@dbt_materialized` to every query.
  - Tag sources: profile-level `query_tags` (a JSON string) and model-level `config(query_tags={…})`. Precedence is model > connection > default. The maximum is 20 tags including defaults.
  - `databricks_tags` sets Unity Catalog table/column governance tags via `ALTER`. These are not billing tags and cannot be removed by dbt.
  - Per-model compute: `databricks_compute` (v1.7.2+).
  - Python models run via `all_purpose_cluster` (Command API or a one-off run), `job_cluster`, `serverless_cluster` or `workflow_job`. Only the job/serverless paths yield `job_run_id` billing.
  - When `liquid_clustered_by` is set, dbt-databricks runs `OPTIMIZE` after each run; disable with `skip_optimize` or `DATABRICKS_SKIP_OPTIMIZE`.
  - dbt prepends a JSON query comment by default (`app`, `dbt_version`, `profile_name`, `target_name`, `node_id`) ([95]). It sits in `statement_text`, which is masked for non-admins ([86]).
- **Workload IDs.** `query_source.job_info` (`job_id`, `job_run_id`, `job_task_run_id`) and `notebook_id` link statements to jobs and notebooks. `job_task_run_timeline.compute_ids` lists the warehouses a task used ([5][9]).
- **Shared all-purpose compute problem.**
  - Billing carries only `cluster_id`, and `run_as` is the cluster creator, not the user.
  - Docs state precise per-job cost is impossible because notebooks, SQL and jobs share the cluster. They advise cluster-level monitoring and treating any split as approximate ([9][2]).
  - `WORKFLOW_RUN` (notebook-launched) usage rolls up to the parent notebook.

## 6. Telemetry latency & retention

| Object | Documented latency | Free retention | Scope / notes |
|---|---|---|---|
| `system.billing.usage` | ORIGINAL typically ≤12 h (new workspaces longer); serverless FAQ: up to 24 h | 365 d | Global; streamable; corrections arrive later as RETRACTION/RESTATEMENT |
| `system.billing.list_prices` | Updated on price change | Indefinite | Global |
| `system.query.history` | Typically ≤1 h (not guaranteed with customer-managed keys) | 365 d | Regional; admin-only by default; GA 2026-09-21 |
| Query History API | Not documented; returns RUNNING/QUEUED (near-real-time) | UNCONFIRMED | ≤30-day window per request; `max_results` <1000 |
| `system.lakeflow.jobs`, `job_tasks`, `job_run_timeline`, `job_task_run_timeline` | Typically ≤1 h, measured from `period_end_time` | 365 d (+ latest SCD2 row kept) | Regional; hourly slices |
| `system.lakeflow.pipelines`, `pipeline_update_timeline` | Not documented | 365 d | Preview |
| `system.compute.clusters` / `warehouses` / `warehouse_events` / `instance_events` / `instance_pools` | Not documented | 365 d | Regional; `instance_*` Public Preview |
| `system.compute.node_timeline` | Not documented; minute rows; <10-min nodes may be missing | 90 d | Classic only |
| `system.compute.node_types` | n/a | Indefinite | |
| `system.access.table_lineage` / `column_lineage` | Not documented | 365 d rolling | Best effort |
| `system.storage.predictive_optimization_operations_history` | ≤2 h (billing up to 24 h) | 180 d | ESTIMATED_DBU |
| Budgets (alerting) | Up to 24 h | n/a | List price |
| Cluster log delivery (classic) | Delivered every 5 min, archived hourly | Customer storage | Driver, worker and event logs ([45]) |

- **General.** System tables are updated throughout the day. New columns can appear without notice. Streaming readers need DBR 16.4+ with `skipChangeCommits`, and VACUUM retention on system tables is 7 days ([6]).
- **Configurable retention** (Beta, 2026-09-09).
  - Account admins can set 30–3,650 d; once opted in, the default becomes 395 d for supported tables.
  - It is free during Beta. Data kept beyond 395 d will incur storage charges at GA.
  - Excluded: `system.data_classification`, `system.data_quality_monitoring` ([6][85]).
- **Access.** Account admin + metastore admin by default; others need `USE CATALOG`, `USE SCHEMA` and `SELECT` ([6]).

## 7. Portability notes

| Workload | Measurable per workload (native) | Ambiguous / missing |
|---|---|---|
| Databricks SQL (dbt SQL models on a SQL warehouse) | Per statement: `system.query.history` metrics + `query_tags` (`@@dbt_model_name`) + `query_source.job_info`. Per warehouse-hour: DBUs by `warehouse_id`. Uptime and cluster count from `warehouse_events`. | Per-statement $ needs apportionment (concurrency, idle until auto-stop, startup, scale-out, IWM). Cache state varies. Pro/classic VM and disk cost is in the cloud bill. DBU/h per size is documented only on Azure. MV/ST refreshes bill elsewhere (serverless pipeline). |
| Serverless jobs | DBUs per `job_run_id` (several rows per hour; sum them). `performance_target`. Statements in `query.history` (`SERVERLESS_COMPUTE`, `query_source.job_info.job_task_run_id`). | No per-task split in billing. Up to 24 h billing delay. Mode changes DBUs. No hardware visibility. |
| Serverless notebooks | DBUs per `notebook_id`/`notebook_path`; `run_as` = session creator; statements in `query.history` | Shared sessions blend users. Idle-release behaviour UNCONFIRMED. |
| Dedicated job compute (classic) | DBUs per `job_run_id`; config from `clusters`; VM-time from `instance_events`/`node_timeline`; `is_photon` | VM, disk and network $ come from the cloud bill. Multi-task shared clusters: no per-task billing. Setup and cleanup are inside the run. Spot eviction. No statement-level system table (Spark UI and log delivery only). |
| Shared all-purpose compute | DBUs per `cluster_id` per hour; `node_timeline` | Per job, notebook or query cost is impossible natively (docs). Concurrent tenants. Idle until auto-termination. `run_as` = creator. |
| Spark Python/Scala on classic | Cluster-level DBUs + node metrics + delivered event logs | No `query.history` rows; attribution needs Spark event-log parsing (schema not researched, UNCONFIRMED) |
| Lakeflow pipelines / MV / ST | DBUs per `dlt_pipeline_id`/`dlt_update_id`; `pipeline_update_timeline`; `query.history` rows (`SERVERLESS_COMPUTE`/`CLASSIC_COMPUTE`) | The incremental-vs-full refresh choice is made by Databricks' cost model. Warehouse tags only inherited since 2026-08-03. |
| Background (predictive optimization, data quality monitoring) | Per-table `ESTIMATED_DBU` (PO table) | `run_as` = Databricks service principal; not attributable to the PR or job that created the table |

- **Cloud differences.**
  - AWS: fleet/spot attributes live in `aws_attributes`.
  - Azure: first-party service billed through Azure. Tags reach Cost Management. `metastore_id` is null. Per-node premium disks are billed hourly.
  - GCP: GCE labels are lowercased and truncated. Several usage_metadata fields are always null (`metastore_id`, `source_region`, `destination_region`, `private_endpoint_name`, `ai_runtime_workload_id`). Workers are n2-highmem-8 ([3][55][32]).

## 8. Documented behaviours that break naive cost estimates

- **Hourly billing grain vs short CI runs.** Usage rows are hour windows. A 90-second query cannot be isolated in billing; only `query.history`/API time can.
- **Serverless multi-row windows and corrections.** Serverless may emit several rows per workload per window. Corrections arrive as `RETRACTION`/`RESTATEMENT` rows. Always sum ([8][1]).
- **Latency.** Billing ≤12 h (up to 24 h for serverless); `query.history` ≤1 h. CI must decide on live API data and reconcile later ([1][40][5]).
- **Warehouse idle tail and startup.**
  - Idle warehouses bill until auto-stop: defaults 10 min (serverless) and 45 min (pro/classic).
  - Pro/classic take about 4 min to start. Serverless standard-mode jobs take 4–6 min.
  - Whether startup minutes are billed is UNCONFIRMED ([35][33][39]).
- **Warehouse autoscaling and concurrency.**
  - Classic/pro add clusters by projected queue minutes, scale down only after 15 min of low load, and allow one cluster per 10 concurrent queries.
  - Serverless IWM scales by prediction.
  - Incremental queries can therefore be free (absorbed by idle capacity) or step-function expensive (a new cluster) ([30][31]).
- **Classic autoscaling.** Optimized vs standard scale-down timers (40 s / 150 s vs 10 min) change the idle cost of the same job ([45]).
- **Shared all-purpose clusters.** No per-job or per-query mapping exists. `run_as` is the creator. `WORKFLOW_RUN` cost goes to the parent notebook ([9][2]).
- **Photon.** It changes the DBU rate on classic compute (multiplier UNCONFIRMED) and is on by default in the UI but off via API unless `runtime_engine=PHOTON`. Faster is not automatically cheaper ([44][49]).
- **Performance mode.** The same serverless job costs different DBUs in STANDARD vs PERFORMANCE_OPTIMIZED ([39]).
- **Spot/preemptible.** The driver is always on-demand; evictions lengthen runs. The VM price differs outside Databricks. `instance_events.availability_type` records spot vs on-demand ([45][12]).
- **Cloud costs outside the Databricks bill.** Classic VMs, disks (for example Azure's 256 GB Premium SSD per warehouse node, billed hourly), networking, cross-region/cross-cloud egress (OpenSharing), and customer-bucket storage. Idle pool instances cost cloud money with no DBUs ([49][31]).
- **List vs contract price.** Every Databricks $ surface is list price; promotional prices change over time (`pricing.promotional`) ([4][64][65]).
- **Caching.** The 24 h result cache (remote cache on serverless) and an uncontrollable disk cache make repeated benchmarks cheaper than production cold runs. Record `from_result_cache` and `read_io_cache_percent` ([74][76]).
- **Work billed elsewhere.**
  - MV/ST refreshes (serverless pipeline DBUs) are not warehouse DBUs, and Databricks may choose a full recompute ([61]).
  - dbt's post-run `OPTIMIZE` for liquid clustering adds work ([94]).
  - Predictive optimization runs as a Databricks service principal ([16b]).
- **Storage growth.** Time-travel retention (30 d log / 7 d files by default) and deep clones grow storage; shallow-clone VACUUM interactions can break clones ([73][71]).
- **DBU multipliers.** Features such as DQM 2X and Data Classification 3X are already baked into `usage_quantity` ([36]).
- **Warehouse recycling and runtime limits.** Warehouses recycle about every 24 h. Serverless runs stop at 7 days ([35][42]).
- **Telemetry gaps.**
  - `node_timeline` may miss nodes that ran under 10 min.
  - Timeline tables slice at clock hours since 2026-01-19; older rows use run-relative slices.
  - `query.history` is regional while billing is global ([12][10][5]).

## 9. Open questions / UNCONFIRMED items

1. `system.billing.cloud_infra_cost`: referenced only by non-primary sources (community, blog, GitHub field solution "cloud-infra-costs"). The guessed doc URL returned 404 and the table is absent from the system-tables list → UNCONFIRMED.
2. SQL warehouse DBU/h per size for **AWS and GCP**, and for **Pro/Classic** on any cloud. Only the Azure serverless table is documented, and the AWS/GCP doc URL redirects to dynamic pricing.
3. $/DBU list prices per SKU and region, and the Photon DBU multiplier. Pricing pages render dynamically; use `system.billing.list_prices` at runtime.
4. Whether cluster or warehouse startup and provisioning time is billed, and any minimum billing increment beyond the "per-second" wording.
5. Whether job tags propagate to `custom_tags` for serverless jobs (docs cover only usage policies).
6. Query History API retention and rate limits. Structure of `job_run_timeline.compute` and `job_task_run_timeline.compute` (populated since Dec 2025, sub-fields undocumented).
7. System-table latency for `compute.*`, `warehouse_events`, lineage and `pipeline_update_timeline` (not stated).
8. `samples.tpch` scale factor and row counts (described as ~1 TB; not independently stated). Whether the `samples` catalog and system tables exist in Free Edition.
9. How serverless notebook idle time is billed (idle release timeout not documented).
10. Whether `query_tags` are masked like `statement_text` for non-admin principals.
11. Whether the DBU rate for a classic cluster differs between spot and on-demand nodes (believed identical; not stated).
12. Whether a documented full query-profile API exists (only UI + JSON download found).
13. AWS/GCP visibility of negotiated DBU price (invoice or contract only?).
14. SKU name strings beyond the doc example `STANDARD_ALL_PURPOSE_COMPUTE`. Enumerate from `list_prices` rather than hard-coding.
15. 5X-Large warehouse status: docs disagree between Beta and Public Preview. Its DBU/h is unlisted.

## 10. Sources

- [1] https://docs.databricks.com/aws/en/admin/system-tables/billing
- [2] https://learn.microsoft.com/en-us/azure/databricks/admin/system-tables/billing
- [3] https://docs.databricks.com/gcp/en/admin/system-tables/billing
- [4] https://docs.databricks.com/aws/en/admin/system-tables/pricing
- [5] https://docs.databricks.com/aws/en/admin/system-tables/query-history
- [6] https://docs.databricks.com/aws/en/admin/system-tables/
- [7] https://docs.databricks.com/aws/en/admin/usage/system-tables
- [8] https://docs.databricks.com/aws/en/admin/system-tables/serverless-billing
- [9] https://docs.databricks.com/aws/en/admin/system-tables/jobs
- [10] https://learn.microsoft.com/en-us/azure/databricks/admin/system-tables/jobs
- [11] https://docs.databricks.com/aws/en/admin/system-tables/jobs-cost
- [12] https://docs.databricks.com/aws/en/admin/system-tables/compute
- [14] https://docs.databricks.com/aws/en/admin/system-tables/warehouses
- [15] https://docs.databricks.com/aws/en/admin/system-tables/warehouse-events
- [16] https://docs.databricks.com/aws/en/admin/system-tables/lineage
- [16b] https://docs.databricks.com/aws/en/admin/system-tables/predictive-optimization
- [17] https://docs.databricks.com/api/workspace/queryhistory/list
- [18] https://docs.databricks.com/api/query-history/v1/query-history
- [19] https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/reference/query-history-commands
- [20] https://docs.databricks.com/aws/en/sql/user/queries/query-history
- [21] https://docs.databricks.com/aws/en/sql/user/queries/query-profile
- [22] https://docs.databricks.com/aws/en/sql/user/queries/query-tags
- [23] https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-conf-mgmt-set-query-tags
- [24] https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-qry-explain
- [25] https://docs.databricks.com/aws/en/optimizations/cbo
- [26] https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-analyze-compute-statistics
- [27] https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-analyze-compute-storage-metrics
- [28] https://docs.databricks.com/aws/en/delta/table-details
- [29] https://docs.databricks.com/aws/en/compute/sql-warehouse/monitor/queries
- [30] https://docs.databricks.com/aws/en/compute/sql-warehouse/warehouse-behavior
- [31] https://learn.microsoft.com/en-us/azure/databricks/compute/sql-warehouse/warehouse-behavior
- [32] https://docs.databricks.com/gcp/en/compute/sql-warehouse/warehouse-behavior
- [33] https://docs.databricks.com/aws/en/compute/sql-warehouse/warehouse-types
- [34] https://docs.databricks.com/gcp/en/compute/sql-warehouse/warehouse-types
- [35] https://docs.databricks.com/aws/en/compute/sql-warehouse/create
- [36] https://learn.microsoft.com/en-us/azure/databricks/resources/pricing (AWS/GCP equivalents https://docs.databricks.com/aws/en/resources/pricing and /gcp/en/resources/pricing redirect to [37])
- [37] https://www.databricks.com/product/pricing (also https://www.databricks.com/product/pricing/databricks-sql; dynamic, no rates extractable)
- [39] https://docs.databricks.com/aws/en/jobs/run-serverless-jobs
- [40] https://docs.databricks.com/aws/en/compute/serverless/
- [41] https://docs.databricks.com/aws/en/compute/serverless/notebooks
- [42] https://docs.databricks.com/aws/en/compute/serverless/limitations
- [43] https://docs.databricks.com/aws/en/spark/conf
- [44] https://docs.databricks.com/aws/en/compute/photon
- [45] https://docs.databricks.com/aws/en/compute/configure
- [46] https://docs.databricks.com/aws/en/compute/clusters-manage
- [47] https://docs.databricks.com/aws/en/compute/pools
- [48] https://docs.databricks.com/aws/en/compute/cluster-config-best-practices
- [49] https://learn.microsoft.com/en-us/azure/databricks/lakehouse-architecture/cost-optimization/best-practices
- [50] https://docs.databricks.com/aws/en/getting-started/concepts
- [51] https://docs.databricks.com/aws/en/getting-started/overview
- [52] https://learn.microsoft.com/en-us/azure/databricks/security/network/classic/vnet-inject
- [53] https://docs.databricks.com/aws/en/admin/account-settings/usage-detail-tags
- [54] https://learn.microsoft.com/en-us/azure/databricks/admin/account-settings/usage-detail-tags
- [55] https://docs.databricks.com/gcp/en/admin/account-settings/usage-detail-tags
- [56] https://docs.databricks.com/aws/en/admin/usage/budget-policies
- [57] https://docs.databricks.com/aws/en/jobs/configure-job
- [58] https://docs.databricks.com/aws/en/jobs/compute
- [59] https://docs.databricks.com/aws/en/jobs/dbt
- [60] https://docs.databricks.com/aws/en/ldp/configure-pipeline
- [61] https://docs.databricks.com/aws/en/ldp/dbsql/materialized
- [62] https://docs.databricks.com/aws/en/ldp/dbsql/materialized-monitor
- [63] https://docs.databricks.com/aws/en/admin/account-settings/usage
- [64] https://docs.databricks.com/aws/en/admin/account-settings/budgets
- [65] https://docs.databricks.com/aws/en/admin/governance-hub/cost
- [66] https://docs.databricks.com/aws/en/admin/usage/
- [67] https://docs.databricks.com/aws/en/admin/usage/default-storage
- [68] https://docs.databricks.com/aws/en/storage/default-storage
- [69] https://learn.microsoft.com/en-us/azure/cost-management-billing/reservations/prepay-databricks-reserved-capacity (Microsoft Cost Management doc on Azure Databricks DBCU; outside the /azure/databricks path)
- [70] https://docs.databricks.com/aws/en/delta/clone
- [71] https://docs.databricks.com/aws/en/delta/clone-unity-catalog
- [72] https://docs.databricks.com/aws/en/sql/language-manual/delta-clone
- [73] https://docs.databricks.com/aws/en/delta/history
- [74] https://docs.databricks.com/aws/en/sql/user/queries/query-caching
- [75] https://docs.databricks.com/aws/en/sql/language-manual/parameters/use_cached_result
- [76] https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-parameters
- [77] https://docs.databricks.com/aws/en/optimizations/disk-cache
- [78] https://docs.databricks.com/aws/en/discover/databricks-datasets
- [79] https://learn.microsoft.com/en-us/azure/databricks/discover/databricks-datasets
- [80] https://docs.databricks.com/aws/en/sql/tpcds-eval
- [81] https://docs.databricks.com/aws/en/getting-started/free-edition
- [82] https://docs.databricks.com/aws/en/getting-started/free-edition-limitations
- [83] https://docs.databricks.com/aws/en/getting-started/free-trial
- [84] https://docs.databricks.com/aws/en/getting-started/free-trial-vs-free-edition
- [85] https://docs.databricks.com/aws/en/release-notes/product/2026/september
- [86] https://docs.databricks.com/aws/en/release-notes/product/2026/august
- [87] https://docs.databricks.com/aws/en/release-notes/product/2026/july
- [88] https://docs.databricks.com/aws/en/release-notes/product/2026/june
- [89] https://docs.databricks.com/aws/en/release-notes/product/2026/may
- [90] https://docs.databricks.com/aws/en/release-notes/product/2026/april (no cost-relevant items)
- [91] https://docs.databricks.com/aws/en/release-notes/product/2026/march (5X-Large Beta, lineage `genie_space_id`/`alert_id`, DBSQL MV performance mode Beta)
- [92] https://docs.databricks.com/aws/en/sql/release-notes/2026 and https://docs.databricks.com/aws/en/sql/release-notes/ (no 2026 cost/query-history items found)
- [94] https://docs.getdbt.com/reference/resource-configs/databricks-configs
- [95] https://docs.getdbt.com/reference/project-configs/query-comment
- [96] https://docs.getdbt.com/docs/core/connect-data-platform/databricks-setup (now shows the dbt v2 profile; no query_tags/cost details)
- Attempted, not usable: https://docs.databricks.com/aws/en/admin/system-tables/cloud-infra-costs (404). Non-primary results (databricks.com/blog, community.databricks.com, github.com/databricks-solutions/cloud-infra-costs) were seen in search but not relied on.
