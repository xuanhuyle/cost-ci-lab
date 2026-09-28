# BigQuery — platform primitives for Cost CI (Phase 1 research notes)

Retrieved 2026-09-28. Documentation research only: no gcloud/bq commands, no BigQuery account used.
Sources: official Google Cloud docs (now served from `docs.cloud.google.com`; every `cloud.google.com/bigquery/docs/*`
URL 301-redirects there; most pages stamped "Last updated 2026-09-24 UTC"), `cloud.google.com/bigquery/pricing`
(static HTML defaults to Iowa/us-central1, so it was also rendered in a browser with the region selector set to
"US (us)"), Cloud Billing docs, and docs.getdbt.com. `[S#]` refers to §9.
Evidence convention (CLAUDE.md): every statement is **DOCUMENTED** at the cited source unless tagged **INFERRED**,
or **UNCONFIRMED** (looked for in primary docs and not found). Quotes are verbatim.

## 1. Summary

- **On-demand, US multi-region:** $6.25/TiB on `total_bytes_billed`. Bytes are rounded up to the MB, with a 10 MB minimum per referenced table and per query, and the first 1 TiB/month is free. Per-job $ is DERIVED exactly from `INFORMATION_SCHEMA.JOBS` (before free tier and discounts). It is also DIRECTLY_MEASURED per job in the detailed billing export ("Analysis metrics have job identifiers"), at about 1 day of latency. [S1,S2,S53]
- **Dry run:** free and uses no slots. It returns bytes only: `totalBytesProcessed` plus `totalBytesProcessedAccuracy` ∈ {UNKNOWN, PRECISE, LOWER_BOUND, UPPER_BOUND}. Where it breaks down:
  - The docs call the billed-bytes estimate "an upper bound".
  - On clustered tables the cost is only known after the query runs.
  - External tables can report 0 bytes; tables with row-level security always report 0.
  - In scripts, dry run stops at the first DDL or control-flow statement, and `CREATE TEMP TABLE` is not supported.
  - It returns no query plan and no slot estimate. [S14,S15,S17,S19,S31]
- **Editions, US PAYG:** Standard $0.04, Enterprise $0.06, Enterprise Plus $0.10 per slot-hour. You are billed for **allocated** slots (baseline + autoscaled), not consumed `total_slot_ms`:
  - Autoscaling works in 50-slot steps and holds for at least 60 s, i.e. a 1-minute minimum, unless you opt in to "fluid scaling" (per-second, no minimum).
  - The docs say it is "not possible to estimate the exact cost of an individual query before execution".
  - Per-job $ under editions does not exist (UNAVAILABLE); only allocations. [S1,S15,S20]
- **Billed capacity** can be rebuilt per second from `RESERVATIONS_TIMELINE`. Cloud Billing adds a $0 "Analysis Slots Attribution" line item (slot-hours per project). [S9,S26]
- **Telemetry:** the JOBS* views are "near real-time" (no number documented) and keep 180 days. The billing export has "no delivery or latency guarantees"; data typically arrives within a day and can take more than 24 h. [S2,S51]
- **Attribution:** job labels are set at submission and flow into billing data. dbt adds job labels only with `query-comment: {job-label: true}`. `query_info.query_hashes.normalized_literals` groups recurring queries. [S2,S44,S58]

## 2. Primitive table

Classes: DIRECTLY_MEASURED = recorded by the platform. DERIVED = deterministic from measured values plus documented rules. ESTIMATED = pre-execution or allocation model. UNAVAILABLE = not exposed.

| Primitive | Object / API (exact names) | Granularity | Latency & retention | Class | Conditions for converting to $ | Src |
|---|---|---|---|---|---|---|
| On-demand billed bytes | `INFORMATION_SCHEMA.JOBS` (= `JOBS_BY_PROJECT`), `JOBS_BY_USER`, `JOBS_BY_FOLDER`, `JOBS_BY_ORGANIZATION` → `total_bytes_billed`; REST `statistics.query.totalBytesBilled` | per job. A SCRIPT parent row sums its children. | "near real-time" (no number); 180 days; needs a region qualifier; partitioned by `creation_time`, clustered by `project_id`,`user_email` | DIRECTLY_MEASURED | $ = `total_bytes_billed/2^40 × regional $/TiB`, on-demand jobs only. Exclude `statement_type='SCRIPT'` rows (double count). Billable iff `error_result` is NULL or `error_result.reason='stopped'`. Value is NULL for row-level-security tables. Google's example uses 50× the rate for CREATE_MODEL. Billing day = `end_time AT TIME ZONE 'PST8PDT'`. Amounts are before free tier and credits. "Informational only" under capacity pricing. | S2,S15 |
| Bytes processed | `total_bytes_processed`; REST `totalBytesProcessed` | per job | as above | DIRECTLY_MEASURED | Not billed as-is: billing rounds up to the MB and applies the 10 MB minimums | S1,S2 |
| Slot time | `total_slot_ms` ("over its entire duration in the RUNNING state, including retries"); REST `statistics.totalSlotMs` | per job | as above | DIRECTLY_MEASURED usage; $ only by allocation (ESTIMATED) | No $ meaning under on-demand. Under editions the bill is for allocated slots, so `slot_ms/3.6e6 × $/slot-h` understates autoscale bills. Docs: "don't use the jobs information schema to match the billing". | S2,S20 |
| Stage plan | `job_stages` (RECORD REPEATED) ↔ REST `queryPlan[]` `ExplainQueryStage`: `slotMs`, `recordsRead`, `recordsWritten`, `shuffleOutputBytes`, `shuffleOutputBytesSpilled`, `parallelInputs`, `completedParallelInputs`, `{wait,read,compute,write}Ms{Avg,Max}`, `startMs`, `endMs`, `steps[]` | per stage | While running, refreshed but "typically won't happen more frequently than every 30 seconds". Absent for dry runs and cache hits; empty with row-level security. | DIRECTLY_MEASURED | No $. The plan can change mid-query; spill is "not deterministic". | S2,S16,S17 |
| Timeline | `timeline` ↔ `QueryTimelineSample`: `elapsedMs`, `totalSlotMs`, `pendingUnits`, `activeUnits`, `completedUnits`, `estimatedRunnableUnits` | per sample | as plan | DIRECTLY_MEASURED | No $. `estimatedRunnableUnits` = work that could use more slots (a contention signal). | S16,S17 |
| Per-second job slots | `JOBS_TIMELINE[_BY_PROJECT\|_BY_USER\|_BY_FOLDER\|_BY_ORGANIZATION]`: `period_start`, `period_slot_ms`, `period_estimated_runnable_units`, `period_shuffle_ram_usage_ratio`, `reservation_id`, `state`, `total_bytes_billed` (completed jobs only) | job × second | near real-time; 180 days | DIRECTLY_MEASURED | Join to `RESERVATIONS_TIMELINE` (`reservation_id` + minute) to apportion billed capacity (ESTIMATED allocation) | S5,S9 |
| Cache hit | `cache_hit`; REST `cacheHit` | per job | — | DIRECTLY_MEASURED | Cache hit ⇒ not charged (on-demand). NULL on a script parent. | S2,S34 |
| Job labels | `labels` (key/value array) in JOBS* and JOBS_TIMELINE*; REST `configuration.labels`; `QueryRequest.labels`; session `@@query_label` | per job; cannot be changed after submission | — | DIRECTLY_MEASURED | "When you add a label to a job, the label is included in your billing data" → $ per label in the billing export | S2,S18,S44 |
| Pricing context | `reservation_id` (`ADMIN_PROJECT:LOCATION.RESERVATION_NAME`), `edition`, `reservation_group_path` | per job (JOBS_TIMELINE: "at the end of this period") | — | DIRECTLY_MEASURED | NULL ⇒ on-demand (or a SCRIPT parent). This decides which $ formula applies. | S2,S5 |
| Recurring-query key | `query_info.query_hashes.normalized_literals` | per job; only successful GoogleSQL, non-cache-hit | — | DIRECTLY_MEASURED | No $. Used for run frequency × per-run cost. | S2 |
| Job shape and lineage | `job_id`, `parent_job_id`, `creation_time`, `start_time`, `end_time`, `statement_type`, `referenced_tables` (non-cache-hit only), `destination_table`, `dml_statistics`, `total_modified_partitions`, `priority`, `user_email`, `principal_subject`, `query`, `error_result`, `job_creation_reason.code`, `session_info`, `bi_engine_statistics`, `query_info.optimization_details` (JOBS_BY_PROJECT only) | per job | — | DIRECTLY_MEASURED | Inputs for frequency and lineage. `JOBS_BY_ORGANIZATION` has no `query` or `dml_statistics`, and leaves out jobs from other orgs that read shared data. | S2,S4 |
| Dry run | `jobs.insert` with `configuration.dryRun=true`, `jobs.query` `dryRun`, `bq --dry_run`. Returns `totalBytesProcessed`, `totalBytesProcessedAccuracy` (UNKNOWN/PRECISE/LOWER_BOUND/UPPER_BOUND), `schema` ("Present only for successful dry run of non-legacy SQL queries"), `undeclaredQueryParameters`. `referencedTables`/`statementType` in dry-run output: UNCONFIRMED. | per query or script, before execution | Synchronous ("A dry run query completes immediately"); "Dry runs don't use query slots, and you are not charged" | ESTIMATED | On-demand $ ≈ apply rounding and minimums × $/TiB, treated as an upper bound. No plan or slots returned, so no $ under editions (dry run gives "approximate bytes processed ... in capacity mode"). | S14,S15,S17,S18 |
| Byte cap | `maximumBytesBilled` (`JobConfigurationQuery`, `QueryRequest`), `bq --maximum_bytes_billed`, dbt profile `maximum_bytes_billed` | per job | Checked against the pre-execution estimate | ESTIMATED (guard) | The query fails "without incurring a charge". On clustered tables the upper-bound estimate can fail queries that would have fit. | S15,S17,S59 |
| Estimate vs actual | REST `statistics.query.estimatedBytesProcessed` ("The original estimate of bytes processed for the job") | per executed job | via `jobs.get`; not in the INFORMATION_SCHEMA column list | DIRECTLY_MEASURED | Would let us back-test dry-run error on production history. When it is populated: UNCONFIRMED. | S17 |
| Reservation config | `INFORMATION_SCHEMA.RESERVATIONS`: `reservation_name`, `slot_capacity` (baseline), `autoscale.current_slots`, `autoscale.max_slots`, `edition`, `ignore_idle_slots`, `target_job_concurrency`, `max_slots`, `scaling_mode`, `labels` | current, per reservation | near real-time; current objects only | DIRECTLY_MEASURED | Edition → $/slot-hour | S8,S25 |
| Billed capacity | `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`: `period_start` (1 min), `slot_capacity`, `slots_assigned`, `slots_max_assigned`, `autoscale`, `period_autoscale_slot_seconds` ("The total slot seconds charged by autoscale for a specific minute"), `per_second_details.{start_time, autoscale_current_slots, autoscale_max_slots, slots_assigned, slots_max_assigned, borrowed_slots, lent_slots}` | reservation × minute, plus a per-second array | "for every minute in real time"; last 180 days, plus change-minutes older than that | DIRECTLY_MEASURED (capacity); DERIVED ($) | $ = autoscale slot-s/3600 × edition PAYG + baseline not covered by commitments × PAYG + commitments × commitment rate. Google's scripts "may not exactly match the bill due to small rounding errors". | S9,S26 |
| Config history | `RESERVATION_CHANGES` (41 days); `ASSIGNMENTS` / `ASSIGNMENT_CHANGES` (`assignee_type`, `assignee_id`, `job_type`, `reservation_name`); `CAPACITY_COMMITMENTS` / `CAPACITY_COMMITMENT_CHANGES` (`slot_count`, `commitment_plan`, `edition`, `state`, `renewal_plan`, `is_flat_rate`) | change events / current | near real-time | DIRECTLY_MEASURED | Tells you which price (PAYG or commitment) applied at time t | S7,S10,S11,S12 |
| Standard billing export | `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>`: `service`, `sku`, `project`, `labels`, `system_labels`, `usage_start_time`/`usage_end_time` (hourly windows), `cost`, `credits`, `consumption_model`, `cost_at_list_consumption_model`, `export_time` | SKU × project × labels × hour | "no delivery or latency guarantees"; "Typically ... within a day, but can sometimes take more than 24 hours"; kept in your own dataset | DIRECTLY_MEASURED ($) | Authoritative $ including credits; no job ids | S51,S52 |
| Detailed billing export | `gcp_billing_export_resource_v1_<...>`: adds `resource.name` and `resource.global_name`. BigQuery: "Analysis metrics have job identifiers and Storage metrics have dataset identifiers"; data from 2023-08-08. | resource (job) × hour | as standard | DIRECTLY_MEASURED (per-job $ for on-demand analysis) | Exact id format, and whether editions slot SKUs carry reservation/job ids: UNCONFIRMED | S53 |
| Analysis Slots Attribution | Cloud Billing line item (reports and export) | "slot hours used per project" | billing latency | DERIVED (by Google) | "It incurs no cost and doesn't affect your invoice totals". Filterable by reservation labels. An allocation key, not a price. | S26,S44 |
| Audit logs | Cloud Logging `BigQueryAuditMetadata` (`JobInsertion`, `JobChange`, `TableDataRead`, `TableDataChange`); legacy `jobCompletedEvent...totalBilledBytes` | per job/event | Latency UNCONFIRMED. "Audit log entries aren't emitted for every job" | DIRECTLY_MEASURED (incomplete) | Docs point to INFORMATION_SCHEMA for complete job counts | S48,S1 |
| Storage bytes | `INFORMATION_SCHEMA.TABLE_STORAGE`, `TABLE_STORAGE_USAGE_TIMELINE` | table | "typically delayed by a few seconds to a few minutes"; expiration/time-travel effects up to a day | DIRECTLY_MEASURED (bytes); DERIVED ($) | × storage price for the dataset's billing model. For billing, docs recommend `TABLE_STORAGE_USAGE_TIMELINE`. | S13,S15 |
| Console monitoring | Admin resource charts; slot estimator ("Model how increasing or reducing max reservation slots might affect performance") | — | at most 30 days | DIRECTLY_MEASURED / ESTIMATED | Performance what-ifs, not $ | S27,S28 |
| Pre-execution slot/plan estimate | None. Dry runs "won't include the additional diagnostic information". No EXPLAIN statement found in the docs (absence UNCONFIRMED). | — | — | UNAVAILABLE | — | S16 |
| Per-job $ under editions | None. Capacity is billed per reservation/SKU; attribution exists only as slot-hours per project. | — | — | UNAVAILABLE (allocation only) | — | S15,S26 |
| dbt Cost Insights (vendor-derived) | dbt platform, Enterprise tiers. On-demand: `total_bytes_billed × price_per_tib`. Capacity: `total_slot_ms × price_per_slot_hour`. Cache hits = $0. | model/job; computed daily from up to the last 7 days | retroactive | DERIVED | "intended for visibility and optimization, not billing reconciliation". The capacity formula ignores 50-slot/60 s granularity (INFERRED). | S60 |

## 3. Billing rules (US multi-region "US (us)" unless stated)

### 3.1 On-demand
- $6.25 per TiB; "0 tebibyte to 1 tebibyte Free per 1 month / account". us-central1 shows the same $6.25. 1 TiB = 2^40 bytes, 1 GiB = 2^30 bytes. [S1]
- "Charges are rounded up to the nearest MB, with a minimum 10 MB data processed per table referenced by the query, and with a minimum 10 MB data processed per query." The troubleshooting page says "10 MiB". The maximum-bytes-billed error example reads "10485760 or higher required", which is 10 MiB. INFERRED: treat 10 MB as 10 MiB. [S1,S15]
- Columnar: you pay for the columns selected. LIMIT does not reduce bytes on non-clustered tables; on clustered tables "scanning stops when enough blocks are scanned". [S1,S15]
- "BigQuery always uses logical (uncompressed) bytes to calculate on-demand query costs", whatever the dataset's storage billing model. External ORC/Parquet: only the columns read, sized as BigQuery types. [S15]
- Not charged:
  - "queries that return an error or ... queries that retrieve results from the cache. For procedural language jobs this consideration is provided at a per-statement level."
  - Dry runs.
  - Caveat: canceling a running query "might incur charges up to the full cost". [S1,S14]
- DML size (q = bytes the statement reads; t = size of the target table before modification; for partitioned tables, t' = total size of the partitions being updated):
  - INSERT: q.
  - UPDATE / DELETE: q + t.
  - MERGE: q if it has only INSERT clauses, otherwise q + t. [S39]
- DDL size: CREATE TABLE, CREATE VIEW and DROP process none. CTAS = "sum of bytes processed for all the columns referenced from the tables scanned". [S40]
- INFORMATION_SCHEMA queries bill at least 10 MB each and "are not cached". [S7]
- Querying shared data bills the querying project; "The data owner is not charged". [S1]
- Free-tier scope conflict: the pricing page says "/ account"; troubleshooting says "Each project is provided with 1 TB of free tier querying per month". UNCONFIRMED which is right.
- Default "Query usage per day" quota is 200 TiB per project (on-demand only). On-demand concurrency: "2,000 slots per project 20,000 slots per organization", with occasional bursts above. [S30,S1]
- Day boundaries: a Cloud Billing "Daily" period starts at midnight US/Canada Pacific. Google's JOBS example buckets by `end_time AT TIME ZONE 'PST8PDT'`. INFORMATION_SCHEMA is in UTC. [S15,S2]

### 3.2 Capacity (editions)
| Edition | PAYG "Default" (model 7754-699E-0EBF) | BigQuery spend-based CUD 1y / 3y (DD83-D9A3-79AF / 4D8D-49A7-C5B1) | Resource (slot) commitments 1y / 3y |
|---|---|---|---|
| Standard | $0.04 /slot-h | $0.036 / $0.032 | not offered |
| Enterprise | $0.06 | $0.054 / $0.048 | $0.048 / $0.036 |
| Enterprise Plus | $0.10 | $0.09 / $0.08 | $0.08 / $0.06 |

Monthly (730 h) PAYG equivalents per slot: $29.20 / $43.80 / $73.00. us-central1 shows the same hourly values. [S1]
- **Billing granularity:** "billed per second with a one-minute minimum duration by default". Opt-in "BigQuery fluid scaling ... per-second billing with no minimum duration" is set per reservation through the admin-project option `region-LOCATION.preflight_fluid_autoscaling_reservations`. Fluid scaling "doesn't change the 50-slot scaling increments". Its launch stage is not stated. [S1,S20,S25]
- **Autoscaler:**
  - "Slots always autoscale to a multiple of 50." "Scaling up is based on actual usage, and is rounded up to the nearest 50 slot increment."
  - "You are charged for the number of scaled slots, not the number of slots used. This charge applies even if the job that causes BigQuery to scale up fails."
  - "Any autoscaled capacity is retained for at least 60 seconds" (the scale-down window; any new peak resets it).
  - It can step by more than 50 at once (e.g. +450). [S20]
- **Baseline:** "always allocated ... and you will always be charged for them". Baseline and max slots must be multiples of 50 "except when covered by excess commitments". Decreases are limited to once an hour in some cases. Standard edition is autoscaling-only (no baseline). [S20,S25,S21]
- **Reservations without autoscaling:** "billing is calculated according to the number of slots provisioned, not the number of slots used". [S15]
- **Slot commitments:**
  - 1 or 3 years; Enterprise and Enterprise Plus only; regional; can be shared across the org; "50-slot minimum and increments of 50 slots"; auto-renew.
  - They cover baseline only: "Slot commitments don't apply to autoscaling slots". Baseline beyond the commitment is billed at PAYG. [S1,S20]
- **Spend-based BigQuery CUDs:** 10% (1y) / 20% (3y) off, committed as $/hour. They apply to "all BigQuery PAYG usage" in a region, but "don't apply to storage or on-demand". Overage is charged at PAYG. Doc inconsistency: the CUD page's example calls $0.036 a 3-year "(20% discount)" for Enterprise, but the pricing table shows $0.048 for the 3y spend CUD ($0.036 is the 3y resource commitment). [S29,S1]
- **Idle slots:**
  - Sources: commitment slots not allocated to any baseline, plus unused baseline. Shared by default within the same admin project, same edition and same region. Autoscaled slots are never shared.
  - Borrowed slots are reclaimed "within a few milliseconds"; the temporary overshoot is not charged.
  - `ignore_idle_slots=true` blocks borrowing, not lending.
  - Related controls: reservation-based fairness (Enterprise and Enterprise Plus), reservation groups, and "predictable" reservations (`max_slots` + `scaling_mode` ALL_SLOTS / IDLE_SLOTS_ONLY / AUTOSCALE_ONLY; Preview).
  - Standard edition has no idle-capacity sharing. [S20,S21,S25,S26]
- **Usage above allocation:** "You aren't billed for slot usage that's greater than your baseline plus scaled slots". BigQuery may burst onto system capacity and then delay results, "ensuring you are never billed above your limit". [S20]
- **Limits:**
  - Standard: max reservation size 1,600 slots; 10 reservations per admin project, up to 16,000 slots per org.
  - Enterprise / Enterprise Plus: bounded by quota. The console purchase quota for the US multi-region is 10,000 slots.
  - Minimum 50 slots per reservation. [S21,S22,S30]
- **Mixing pricing models:**
  - Editions and on-demand can run side by side per project. Projects with no assignment default to on-demand; an assignment to `none` forces on-demand (QUERY jobs only).
  - A single query can override its reservation via the `reservation` field; the value `none` "Forces the query to use on-demand billing" when `reservation_override_mode=ALLOW_ANY_OVERRIDE`. [S21,S20,S24,S18]
- **Priority under regional contention:** Ent+/Ent baselines and commitments first, then Ent+ autoscale, then Ent autoscale, then Standard and on-demand. [S20]
- **What slot-ms means for billing: confirmed** — editions bill allocated (baseline + scaled) slots, not consumed slot-ms. [S15,S20] Conflicting text: the `jobs.query` response describes `totalSlotMs` as "Number of slot ms the user is actually billed for". This is a doc inconsistency (UNCONFIRMED meaning). [S18]
- Legacy flat-rate "is no longer offered as of July 5, 2023" (see `is_flat_rate` on commitments). [S1,S12]

### 3.3 Storage (per GiB-month; first 10 GiB free) [S1,S15,S42]
- **US multi-region:** active logical $0.02; long-term logical $0.01; active physical $0.04; long-term physical $0.02. By comparison, us-central1 shows $0.000031507/GiB-hour active logical (≈ $0.023/month), so region matters.
- "prorated per MiB, per second". Data becomes long-term after 90 consecutive days unmodified, judged per partition. Any modification moves it back to active: DML, loads, ALTER, or even label/description changes.
- **Physical billing:** time travel (48–168 h, default 7 days) and fail-safe (7 days) are "charged separately at active storage rates"; under logical billing they are included. A billing-model change takes 24 h to apply and cannot be changed again for 14 days.
- Temporary session/multi-statement tables are billed as active storage only; cached-result tables are free. [S1]

### 3.4 BI Engine
- $0.0416 per GiB-hour of memory in us-central1. The BI Engine region list on the pricing page has no "US (us)" entry. [S1]
- Editions commitments bundle BI Engine memory at no extra cost: 100 slots → 5 GiB … 2,000 slots → 100 GiB (maximum per org). [S1]
- Not available in Standard edition. [S21]
- Effect on query billing: under on-demand, "stages that use BI Engine are charged for 0 scanned bytes". Under editions, "the first stage consumes no BigQuery reservation slots". Stages BI Engine cannot accelerate fall back to normal slots. [S1,S49]

## 4. CI / isolation primitives

- **Table clones:**
  - "initially no storage cost"; you pay only for data added or changed.
  - Reclustering of the base table: "This causes the oldest of the base table's clones to be charged the full storage amount of the modified partition."
  - Must be in the same region and org. Views, materialized views and external tables cannot be cloned. Streaming-buffer and time-travel data are not included.
  - Clone creation counts against copy-job limits, and copy jobs are free ("You are not charged for copying a table"). INFERRED: creating a clone costs no compute.
  - INFERRED: querying a clone bills logical bytes like any table, so clones cut CI storage cost, not CI compute cost. [S37,S1,S15]
- **Snapshots:** read-only; can capture any point in the last 7 days; billed only for the storage delta. Copying a snapshot or clone means "a full copy of the table is created". [S38]
- **Partition pruning:**
  - Pruned partitions are not billed.
  - The filter must be a constant expression on the isolated partition column; a small set of built-in functions is allowed.
  - `WHERE t1.ts = (SELECT ...)` "is not a constant expression" and does not prune. `OR` with a non-partition predicate defeats pruning. No pruning through functions on integer-range partitions.
  - "You can use dry run to verify if partition pruning is supported". `require_partition_filter` exists. [S32]
- **Clustering (block pruning):**
  - Bytes billed = the blocks actually scanned. "you don't receive an accurate query cost estimate before query execution"; "The cost of queries over clustered tables can only be determined after the query is run".
  - A clustered table referenced several times is billed once per filter.
  - Automatic reclustering is a free operation and "has no effect on query capacity". [S31]
- **`TABLESAMPLE SYSTEM (n PERCENT)`** (Preview):
  - Samples whole blocks; tables are split into blocks "if they are larger than about 1 GB", so small tables are read in full.
  - "you are charged for reading the data that is sampled". INFERRED: on large tables, on-demand bytes drop roughly in proportion to n.
  - Results are never cached. Samples are more biased on partitioned/clustered tables. A sampled table can appear only once per statement; no views, subqueries or row-level security. [S33]
- **Query cache:**
  - About 24 h, best-effort.
  - Not used when: a destination table is set; referenced tables changed; the streaming buffer has data; non-deterministic functions are used (e.g. `CURRENT_DATE`); wildcard tables are queried; row-level security applies; or the query text differs at all (including whitespace or comments).
  - Disable with `useQueryCache=false` or `bq --nouse_cache`. Cross-user caching exists only in Enterprise and Enterprise Plus.
  - INFERRED: dbt table/incremental builds write to destinations, so they never hit the cache. [S34,S17,S21]
- **Dry runs:** free and use no slots, so CI can dry-run every changed statement at $0. Any dry-run-specific quota or rate limit: UNCONFIRMED. [S14]
- **Sandbox:**
  - No credit card needed.
  - Limits: 10 GiB lifetime storage; 1 TiB of queries per month; tables expire after 60 days.
  - Not supported: streaming, DML (so no MERGE-based incremental models), Data Transfer Service. Whether reservations are available: UNCONFIRMED. [S35]
- **Public datasets:**
  - Google pays storage and you pay for queries; "The first 1 TB per month is free".
  - Sample tables live in the US multi-region (`bigquery-public-data.samples`: gsod, github_nested, github_timeline, natality, shakespeare, trigrams, wikipedia).
  - Official docs query `bigquery-public-data.thelook_ecommerce.{order_items,products,users}`, and `goog_blockchain_ethereum_mainnet_us.transactions` (filtered on `block_timestamp`).
  - Table sizes and partitioning/clustering of these datasets: UNCONFIRMED (not documented). TPC-H/TPC-DS inside `bigquery-public-data`: UNCONFIRMED (not found). [S36,S61,S56]
- **Isolating CI compute:**
  - Per-query `reservation` override (needs `bigquery.reservations.use`).
  - Principal-based assignments (Preview) can route a CI service account to its own reservation.
  - A `none` assignment forces on-demand.
  - Per-project caps (`scheduling_policy_max_slots`, max concurrency).
  - Cost guards: `maximumBytesBilled`; custom per-project or per-user daily quotas. [S24,S18,S25,S15]

## 5. Attribution primitives

- **Job labels:**
  - Limits: up to 64 per resource; keys 1–63 chars; values ≤63 chars; lowercase letters, digits, `_` and `-` only; "Label keys must start with a letter".
  - "You cannot add labels to or update labels on pending, running, or completed jobs."
  - Job labels are included in billing data. Dataset labels go to storage billing but "not in your job-related billing data"; "Table and view labels are not included in billing data".
  - Session labels: `SET @@query_label = "k1:v1,k2:v2"`, or the `connectionProperties` `query_label`. [S43,S44,S18]
- **Reservation labels:** they appear in billing data and filter the "Analysis Slots Attribution" SKU. That SKU "only records slot usage"; reservation labels cannot filter the Reservations API SKUs. [S44]
- **dbt-bigquery:**
  - Default comment, prepended to each query: `/* {"app": "dbt", "dbt_version": ..., "profile_name": ..., "target_name": ..., "node_id": "model.<proj>.<name>"} */`. It can be parsed from `JOBS.query`, but `JOBS_BY_ORGANIZATION` has no `query` column.
  - `query-comment: {job-label: true}` (BigQuery only) "will include the query comment items, if a dictionary, or the comment string, as job labels ... in addition to labels specified in the BigQuery-specific config".
  - The `labels` model config labels tables and views; "By default, labels are not applied to jobs directly". Label "entries ... larger than 63 characters are truncated". The docs show a `query_comment(node)` macro that merges `node.config.labels` into the job labels.
  - How dbt sanitises label values (e.g. the dots in `node_id`): UNCONFIRMED.
  - A `reservation` config (target / project / model level) routes dbt jobs to a given reservation. [S57,S58]
- **dbt incremental strategies:**
  - `merge` (the default) "requires scanning all source tables referenced in the model SQL, as well as destination tables".
  - `insert_overwrite` runs as a multi-statement script: temp table, then `DECLARE`, then `MERGE`. The dynamic mode adds introspection queries; static `partitions` avoids them.
  - `copy_partitions: true` uses the copy API, which "does not incur any costs for inserting the data".
  - `microbatch` is also supported. [S57]
- **Recurring queries:** `normalized_literals` "ignores comments, parameter values, UDFs, and literals". It changes "when underlying views change, or if the query implicitly references columns, such as SELECT *, and the table schema changes". [S2]
- **Scripts:** the parent row has `statement_type='SCRIPT'` and `reservation_id` NULL; children carry `parent_job_id`. Exclude SCRIPT rows when summing. Whether child jobs inherit the parent's labels: UNCONFIRMED. [S2]
- **Shared capacity:** Google documents only three routes:
  - `RESERVATIONS_TIMELINE` for reservation charges;
  - "Analysis Slots Attribution" (slot-hours per project);
  - JOBS_TIMELINE slot-ms joined per second to `RESERVATIONS_TIMELINE`.
  Fair scheduling shares slots equally across projects first, then across jobs, so a job's slot-ms and duration depend on what else is running. [S2,S9,S20,S26]
- **Scheduled queries:**
  - They are transfer configs (`data_source_id` `scheduled_query`) and "are always run as batch query jobs".
  - They run as the creator or as a service account, and are billed to the project that holds the scheduled query.
  - "Scheduled queries are priced the same as manual BigQuery queries".
  - Job-id pattern and any automatic labels: UNCONFIRMED. [S45]
- **Dataform:** workflow invocation actions expose `bigqueryAction.jobId` ("The ID of the BigQuery job that executed the SQL in sql_script"), which can be joined to JOBS. Automatic labels: UNCONFIRMED. [S55]
- **Optional job creation mode** (`jobCreationMode=JOB_CREATION_OPTIONAL`): no job resource is created; JOBS rows then carry the `queryId` in `job_id`. [S14,S2]
- **System labels in billing:** `goog-bq-feature-type` (values `BQ_STUDIO_NOTEBOOK`, `SPARK_PROCEDURE`) and BQML's `bigquery.googleapis.com/bqml`. [S15,S1]

## 6. Telemetry latency & retention

| Source | Documented latency | Retention |
|---|---|---|
| JOBS / JOBS_BY_USER / JOBS_BY_FOLDER / JOBS_BY_ORGANIZATION | "near real-time"; includes running jobs. Numeric latency UNCONFIRMED. | 180 days. History from before a project's org migration is not accessible. |
| JOBS_TIMELINE* | "near real-time", one row per job-second | 180 days |
| Query plan/timeline of a running job | refreshed "typically won't happen more frequently than every 30 seconds" | as JOBS |
| RESERVATIONS / ASSIGNMENTS / CAPACITY_COMMITMENTS | "near real-time" | current objects only; deleted ones drop out after the retention period |
| RESERVATIONS_TIMELINE | "for every minute in real time", plus per-second details | last 180 days (older minutes kept only if they contain changes) |
| RESERVATION_CHANGES | "near real-time" | 41 days |
| TABLE_STORAGE | seconds to minutes; up to 1 day for expiration/time-travel effects | current |
| Admin resource charts / slot estimator | "updated in real time" | 30 days |
| Standard / detailed billing export | No guarantees. "Typically ... within a day, but can sometimes take more than 24 hours". After first enabling: "a few hours". Backfill: up to 5 days. Tags: up to 1 h. Project info may be missing for 24 h after project creation. | Your own dataset (the Google-provided FOCUS export has a 2-year TTL) |
| Pricing export | up to 48 h after enabling | your dataset |
| Cloud Audit Logs | UNCONFIRMED | UNCONFIRMED (Cloud Logging settings) |

## 7. Documented behaviours that break naive estimates

1. **Dry-run bytes ≠ billed bytes.**
   - The estimate is an "upper bound"; on clustered tables the cost is unknown until the query runs.
   - Federated/external queries can report "a lower bound of 0 bytes"; row-level-security tables always return 0.
   - Dry runs of INFORMATION_SCHEMA queries can be "significantly higher than the actual bytes processed", because only the `creation_time` partition filter is applied.
   - Rounding and the 10 MB minimums must still be added on top. [S15,S14,S31,S2]
2. **Multi-statement dry runs are partial** (this covers dbt `insert_overwrite` scripts):
   - Validation stops after the first DDL statement, and "Dry runs of CREATE TEMP TABLE statements aren't supported".
   - It stops at FOR/IF/WHILE and after EXECUTE IMMEDIATE.
   - DML byte estimates "are based on original table sizes".
   - Variables in partition filters cannot be evaluated.
   - "Dry runs operate on a best-effort basis".
   - INFERRED: a dbt incremental script cannot be priced by dry-running it as submitted; its statements would need to be dry-run individually. [S19,S57]
3. **Pruning that happens only at runtime:** subquery or dynamic partition predicates do not prune. History-based optimizations (e.g. `semi_join_reduction`) can change execution between runs. INFERRED: static analysis cannot infer bytes for subquery-driven incremental filters. [S32,S46]
4. **DML and MERGE costs:**
   - UPDATE, DELETE and MERGE-with-update also bill the whole target table (or all updated partitions), not just what they read.
   - Fine-grained DML (Preview) pushes deleted-data cleanup into later background jobs, billed on-demand or to a BACKGROUND reservation. INFERRED: that cost is not attributed to the job that caused it. [S39,S41]
5. **Slot-ms varies from run to run:**
   - History-based optimizations: example series of 60 → 30 → 20 slot-seconds over repeated executions.
   - Internal retries: up to 3 attempts, and `total_slot_ms` includes them (use `finalExecutionDurationMs` to detect).
   - Fair scheduling under concurrency; lower priority for Standard/on-demand under regional contention; speculative execution; non-deterministic spill.
   - INFERRED: a single CI run of new SQL is not a steady-state measurement. [S46,S30,S20,S16]
6. **Autoscaler granularity:** 50-slot rounding and a 60 s scale-down window; "Avoid sending queries one at a time, since each query scales the reservation where it will remain scaled for a 1-minute minimum". Failed jobs still trigger billed scale-ups. INFERRED: a change's marginal $ depends on co-scheduled load (supports hypothesis HD). [S20]
7. **Prepaid capacity absorbs growth:** extra load that fits in idle baseline, commitments or an unused spend-based CUD costs $0 at the margin until saturated; after that, autoscale or overage is billed at PAYG (INFERRED from S20, S29). Idle slots never cross editions, and Standard edition has no idle sharing. [S20,S21]
8. **Cache:** changes that modify tables invalidate downstream cache hits; non-deterministic functions disable caching; cross-user caching only in Enterprise and Enterprise Plus. INFERRED: a PR can change the cost of downstream BI queries through cache behaviour alone. [S34,S21]
9. **BI Engine:** accelerated stages bill 0 bytes on-demand, unaccelerated stages fall back to slots, and the memory reservation is billed separately per GiB-hour. [S1,S49]
10. **Storage side effects:**
    - New tables, or switching a view to a table.
    - Frequent overwrites under physical billing retain the replaced data for time travel and fail-safe.
    - Any modification returns long-term data to active storage (about 2× the price).
    - Delta billing on clones/snapshots jumps after base-table reclustering. [S15,S37,S42]
11. **Materialized views:** automatic refresh is billed to the MV's own project; dry runs apply MV query rewriting. [S47]
12. **INFORMATION_SCHEMA-derived $ vs the invoice** (Google's own reconciliation list): free tier, SCRIPT double-counting, credits/discounts, bytes hidden on row-level-security tables, BQML rates, wrong regional price, Pacific vs UTC day boundaries. [S15]
13. `reservationUsage[]` is deprecated: it "reported misleading information and will no longer be populated". [S17]

## 8. Open questions / UNCONFIRMED items

- Numeric ingest latency of JOBS / JOBS_TIMELINE (docs say only "near real-time").
- When `totalBytesProcessedAccuracy` is PRECISE vs UPPER_BOUND (the values are listed but no rules are given). Whether dry-run responses include `referencedTables`, `statementType` or `totalPartitionsProcessed`. INFERRED only: a DML dry run includes the t term (the DML docs point to "Check the estimated cost" as the way to preview bytes).
- When `estimatedBytesProcessed` is populated on executed jobs, and whether it can be queried in bulk (it is not in the INFORMATION_SCHEMA column list).
- `final_execution_duration_ms` is cited by the quotas page but missing from the JOBS schema table.
- Rounding unit: MB (pricing page) vs MiB (troubleshooting page, error text). Free-tier scope: per account vs per project.
- `jobs.query` `totalSlotMs` described as "actually billed for" vs allocation-based billing.
- Detailed export: exact `resource.name` format for analysis jobs; whether editions/autoscale SKUs carry reservation or job ids; time granularity of Analysis Slots Attribution.
- Fluid scaling: launch stage (not stated); whether it changes scale-down behaviour beyond billing.
- Label inheritance from a SCRIPT parent to its children; dbt label sanitisation; whether scheduled queries or Dataform add labels automatically; the scheduled-query job-id pattern.
- BI Engine price for the US multi-region (only single regions are listed).
- Sizes and layout of `thelook_ecommerce` and the crypto datasets; whether TPC-H/TPC-DS exist in `bigquery-public-data`.
- Dry-run quotas or rate limits; audit-log latency and retention; whether the sandbox can use reservations.
- The BigQuery CUD doc example conflicts with the pricing table (see §3.2).

## 9. Sources

Retrieved 2026-09-28. `cloud.google.com/bigquery/docs/X` redirects to `docs.cloud.google.com/bigquery/docs/X`.
- S1 BigQuery pricing — https://cloud.google.com/bigquery/pricing
- S2 JOBS view — https://docs.cloud.google.com/bigquery/docs/information-schema-jobs
- S3 JOBS_BY_USER — https://docs.cloud.google.com/bigquery/docs/information-schema-jobs-by-user
- S4 JOBS_BY_ORGANIZATION — https://docs.cloud.google.com/bigquery/docs/information-schema-jobs-by-organization
- S5 JOBS_TIMELINE — https://docs.cloud.google.com/bigquery/docs/information-schema-jobs-timeline
- S6 JOBS_TIMELINE_BY_ORGANIZATION — https://docs.cloud.google.com/bigquery/docs/information-schema-jobs-timeline-by-organization
- S7 INFORMATION_SCHEMA intro — https://docs.cloud.google.com/bigquery/docs/information-schema-intro
- S8 RESERVATIONS — https://docs.cloud.google.com/bigquery/docs/information-schema-reservations
- S9 RESERVATIONS_TIMELINE — https://docs.cloud.google.com/bigquery/docs/information-schema-reservation-timeline
- S10 RESERVATION_CHANGES — https://docs.cloud.google.com/bigquery/docs/information-schema-reservation-changes
- S11 ASSIGNMENTS — https://docs.cloud.google.com/bigquery/docs/information-schema-assignments
- S12 CAPACITY_COMMITMENTS — https://docs.cloud.google.com/bigquery/docs/information-schema-capacity-commitments
- S13 TABLE_STORAGE — https://docs.cloud.google.com/bigquery/docs/information-schema-table-storage
- S14 Run a query (dry run, optional job creation) — https://docs.cloud.google.com/bigquery/docs/running-queries
- S15 Estimate and control costs — https://docs.cloud.google.com/bigquery/docs/best-practices-costs
- S16 Query plan and timeline — https://docs.cloud.google.com/bigquery/docs/query-plan-explanation
- S17 REST Job resource — https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/Job
- S18 REST jobs.query — https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/jobs/query
- S19 Multi-statement queries — https://docs.cloud.google.com/bigquery/docs/multi-statement-queries
- S20 Understand slots (autoscaling, fluid scaling, idle slots) — https://docs.cloud.google.com/bigquery/docs/slots (target of `slots-autoscaling-intro`)
- S21 Editions — https://docs.cloud.google.com/bigquery/docs/editions-intro
- S22 Reservations intro — https://docs.cloud.google.com/bigquery/docs/reservations-intro
- S23 Workload management — https://docs.cloud.google.com/bigquery/docs/reservations-workload-management
- S24 Reservation assignments — https://docs.cloud.google.com/bigquery/docs/reservations-assignments
- S25 Manage reservations (fluid scaling option, predictability) — https://docs.cloud.google.com/bigquery/docs/reservations-tasks
- S26 Monitor reservations (slot metrics, cost attribution) — https://docs.cloud.google.com/bigquery/docs/reservations-monitoring
- S27 Admin resource charts — https://docs.cloud.google.com/bigquery/docs/admin-resource-charts
- S28 Slot estimator — https://docs.cloud.google.com/bigquery/docs/slot-estimator
- S29 BigQuery spend-based CUDs — https://docs.cloud.google.com/bigquery/docs/bigquery-cud
- S30 Quotas and limits — https://docs.cloud.google.com/bigquery/quotas
- S31 Clustered tables — https://docs.cloud.google.com/bigquery/docs/clustered-tables
- S32 Query partitioned tables — https://docs.cloud.google.com/bigquery/docs/querying-partitioned-tables
- S33 Table sampling — https://docs.cloud.google.com/bigquery/docs/table-sampling
- S34 Cached results — https://docs.cloud.google.com/bigquery/docs/cached-results
- S35 Sandbox — https://docs.cloud.google.com/bigquery/docs/sandbox
- S36 Public datasets — https://docs.cloud.google.com/bigquery/public-data
- S37 Table clones — https://docs.cloud.google.com/bigquery/docs/table-clones-intro
- S38 Table snapshots — https://docs.cloud.google.com/bigquery/docs/table-snapshots-intro
- S39 DML syntax (on-demand size calculation) — https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/dml-syntax
- S40 DDL (on-demand size calculation) — https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/data-definition-language
- S41 DML intro (fine-grained DML) — https://docs.cloud.google.com/bigquery/docs/data-manipulation-language
- S42 Datasets intro (storage billing models) — https://docs.cloud.google.com/bigquery/docs/datasets-intro ; https://docs.cloud.google.com/bigquery/docs/updating-datasets
- S43 Labels intro — https://docs.cloud.google.com/bigquery/docs/labels-intro
- S44 Adding labels (jobs, sessions, reservations) — https://docs.cloud.google.com/bigquery/docs/adding-labels
- S45 Scheduling queries — https://docs.cloud.google.com/bigquery/docs/scheduling-queries
- S46 History-based optimizations — https://docs.cloud.google.com/bigquery/docs/history-based-optimizations
- S47 Materialized views — https://docs.cloud.google.com/bigquery/docs/materialized-views-intro
- S48 Audit logs — https://docs.cloud.google.com/bigquery/docs/reference/auditlogs
- S49 BI Engine intro — https://docs.cloud.google.com/bigquery/docs/bi-engine-intro
- S50 Export Cloud Billing data to BigQuery — https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery
- S51 Billing data tables (frequency of data loads) — https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables
- S52 Standard usage cost schema — https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage
- S53 Detailed usage cost schema — https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage
- S54 Spend-based CUD consumption models — https://docs.cloud.google.com/docs/cuds-multiprice
- S55 Dataform workflow invocation actions — https://docs.cloud.google.com/dataform/docs/reference/mcp/tools_list/query_workflow_invocation_actions
- S56 Blockchain Analytics datasets — https://docs.cloud.google.com/blockchain-analytics/docs/supported-datasets
- S57 dbt BigQuery configurations — https://docs.getdbt.com/reference/resource-configs/bigquery-configs
- S58 dbt query-comment — https://docs.getdbt.com/reference/project-configs/query-comment
- S59 dbt Connect BigQuery (platform; `maximum_bytes_billed`) — https://docs.getdbt.com/docs/platform/connect-data-platform/connect-bigquery
- S60 dbt Cost Insights — https://docs.getdbt.com/docs/explore/cost-insights
- S61 Analyze data with Gemini (uses `thelook_ecommerce`) — https://docs.cloud.google.com/bigquery/docs/gemini-analyze-data
- Also consulted: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup ; https://docs.cloud.google.com/bigquery/docs/query-insights ; https://docs.getdbt.com/docs/local/connect-data-platform/bigquery-setup (now documents "dbt v2"; no `maximum_bytes_billed`)
