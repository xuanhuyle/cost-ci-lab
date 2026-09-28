# dbt change-detection mechanics and prior art for Cost CI

Research date: 2026-09-28. All sources fetched on that date; URLs in section 11.
Scope: (A) dbt change detection, lineage, CI, artifacts and attribution mechanics; (B) prior art for
pre-merge cost estimation. Part A uses only docs.getdbt.com, the dbt JSON schemas and dbt-labs GitHub
repos (plus adapter source code, including databricks/dbt-databricks). Part B uses vendor docs and papers.

**Evidence labels** (mapped to the project vocabulary in `CLAUDE.md`):
- `DOCUMENTED`: stated in official docs, a published schema or the paper text.
- `DOCUMENTED-SRC`: read from source code on the named branch. Primary evidence, but it can change without notice.
- `CLAIMED`: a vendor marketing page or README claim with no mechanism found. Treat it as `UNVALIDATED`.
- `INFERRED`: my reasoning from the cited evidence. The source does not say it.
- `UNCONFIRMED`: I looked and could not confirm it. Treat it as `UNVALIDATED`.

**2026 landscape (read first)**
- dbt v2.0 is GA as of 2026-09-16: "the dbt Fusion engine has graduated into General Availability under its new name: dbt". `DOCUMENTED` (dbt blog). The `main` branch of the dbt-core repo now holds the Rust v2.0 source (Apache 2.0), and "dbt v1 development has moved to the `1.latest` branch". `DOCUMENTED-SRC` (repo README). v1 code below is from `1.latest`.
- v2 writes a `v12` manifest compatible with v1; "`state:modified`, `--defer`, and cross-environment `dbt docs generate` work across mixed dbt v2 and dbt v1 environments". v2 adapters: BigQuery, Databricks, Redshift, Snowflake, ClickHouse (private beta), Spark (CLI only, beta), DuckDB (CLI only). `DOCUMENTED`
- On 2026-06-01, dbt Labs and Fivetran announced "dbt State" as the successor to state-aware orchestration. `DOCUMENTED`

---
## Part A — dbt

### A1. `state:` selection: what counts as "modified"

| Selector | Documented definition (`DOCUMENTED`) | v1 implementation (`DOCUMENTED-SRC`, `selector_methods.py`, `nodes.py`) |
|---|---|---|
| `state:new` | "no node with the same `unique_id` in the comparison manifest" | `old is None` |
| `state:old` | node with same `unique_id` exists | `old is not None` |
| `state:modified` | "All new nodes, plus any changes to existing nodes" | `not same_contents(old)` OR upstream macro changed OR contract changed |
| `state:unmodified` | "All existing nodes with no changes" | negation |
| `.body` | "Changes to node body (e.g. model SQL, seed values)" | `self.raw_code == other.raw_code`; seeds compare file checksum |
| `.configs` | "Changes to any node configs, excluding `database`/`schema`/`alias`/`tags`/`meta`" | `config.same_contents(unrendered_config, old.unrendered_config)` |
| `.relation` | database/schema/alias "irrespective of `target` values or `generate_x_name` macros" | compares `unrendered_config` database/schema/alias |
| `.persisted_descriptions` | descriptions "if and only if `persist_docs` is enabled" | compares descriptions only when persist_docs is on |
| `.macros` | "Changes to upstream macros (whether called directly or indirectly by another macro)" | text compare of `macro_sql`, walked recursively through `depends_on.macros` |
| `.contract` | contract column `name`/`data_type`; removing a column or changing a type is breaking and raises an error | sha256 over sorted columns, data types and constraints (plus materialization when it enforces constraints) |

- No sub-selector newer than these six is documented; the v1 `state_checks` dict contains exactly these keys plus new/old/modified/unmodified. `DOCUMENTED` / `DOCUMENTED-SRC`
- **The core rule is textual, pre-Jinja comparison.** `same_contents` = `same_body` ∧ `same_config` ∧ `same_persisted_description` ∧ `same_fqn` ∧ `same_database_representation` ∧ `same_contract`, and `same_body` is `raw_code` equality. Compiled SQL is **not** compared. `DOCUMENTED-SRC`
- **Macros.** A macro is modified when its `macro_sql` text differs or it was added or removed; every node depending on it, directly or through other macros, is flagged. `DOCUMENTED-SRC`, plus the docs caveat "dbt will mark modified any resource that depends on a changed macro, or on a macro that depends on a changed macro". Because `manifest.macros` includes package macros, a package upgrade that changes macro text should flag its dependents. `INFERRED`
- **Ignored or conditional fields.** `tags`/`meta` changes are "metadata only" and never trigger; `description` counts only with `persist_docs`. Seeds under 1 MiB compare a content hash; seeds of 1 MiB or more compare only their path, with a warning. The selector also covers source `freshness`/`quoting`, exposure `maturity`, `access`, `deprecation_date` and `latest_version`. `DOCUMENTED`
- **Behavior flag `state_modified_compare_more_unrendered_values`.** It compares unrendered values (literal Jinja text) for YAML configs containing Jinja and for source database/schema. Opt-in from 1.9, default `true` in 1.12.0 (dbt platform track 2026.09), always on in v2; the docs call it a "Selection-set change with potential CI impact". If the baseline was built before the flag was on, "every node whose YAML config contains Jinja will appear as `state:modified`" on the first comparison. `DOCUMENTED`

**Blind spots (false negatives). These matter most for Cost CI:**
1. **Values of `var` / `env_var`.** Quote: "dbt is unable to identify that lineage in such a way that it can include the model in `state:modified` because the `var` or `env_var` value has changed." `DOCUMENTED`. Issue dbt-core#4304 (opened 2021-11-18) was still open on 2026-09-28. `DOCUMENTED-SRC`. The docs' line "It's likely that the model will be marked modified if the change in variable results in a different configuration" predates unrendered comparison; with literal-text comparison now the default (1.12+), a var value feeding a config should no longer change the compared text. `INFERRED` / `UNCONFIRMED`
2. **Target-dependent Jinja** (`{% if target.name == 'prod' %}`, dev-only limits, `generate_schema_name`). Only a change to `raw_code` triggers detection. `DOCUMENTED-SRC`. CI-compiled SQL can also differ from what prod will run: "If you apply environment-specific limits in development but not in production, you may select more data than expected". `DOCUMENTED` (defer page)
3. **Data-dependent SQL** (`run_query`, `dbt_utils.get_column_values`, introspective macros) **and data changes in general**: "`state:modified` ... only detect[s] changes to your project's code, configuration, or manifest-relevant metadata — not changes to the data itself". `DOCUMENTED`. Changes in introspective query results are invisible. `INFERRED` from the raw-text rule.
4. **Operational pitfalls.** False positives come from env-aware config (the flag mitigates this). Pointing `--state` at the same path as `--target-path` lets the baseline manifest be overwritten before it is read. `DOCUMENTED`

**Contrast: the dbt platform and v2 use rendered SQL.** State-aware orchestration uses "Compiled SQL diffs that ignore non-meaningful changes like whitespace and comments". dbt State "compares rendered SQL ... by parsing the rendered SQL into a syntax tree and comparing the hash. Any change to the rendered SQL — including from non-deterministic macros or environment variables — triggers a rebuild." `DOCUMENTED`. The v2 CLI's `state:modified`, by contrast, keeps parity with v1's `raw_code` semantics; the Fusion changelog says: "Populate manifest raw_code with verbatim source at parse time, restoring parity with dbt-core for same_body/state:modified". `DOCUMENTED-SRC` (dbt-fusion CHANGELOG)

**Other selectors and operators**
- `result:<status>` string-matches the status in the previous `run_results.json`. `DOCUMENTED-SRC`. The docs show only `result:error` (any resource) and `result:fail` (tests only; `result:fail+` returns only the test). `DOCUMENTED`. Other statuses (`warn`, `skipped`) are undocumented but matched by the code. `DOCUMENTED-SRC`
- `source_status:fresher` needs `sources.json` from `dbt source freshness` in both states; compares `max_loaded_at`. `DOCUMENTED` / `DOCUMENTED-SRC`
- Graph operators: `+` adds ancestors or descendants, `n+` limits depth, and `@` "will also include all ancestors of all descendants", which the docs call "useful in continuous integration environments". `DOCUMENTED`
- Configuration: `--state` or `DBT_ENGINE_STATE` (v1.11+), and `--defer-state` for a separate manifest. `DOCUMENTED`
- **Implication for Cost CI.** `dbt ls -s state:modified+ --state <prod-artifacts>` is a cheap starting set but not sufficient; Cost CI should also render both sides and diff the compiled SQL, as dbt State does. `INFERRED`

### A2. `--defer`, `--favor-state`, `dbt clone`, Slim CI, dbt platform CI, v2 and dbt State

- **`--defer`.** `ref`/`function` resolve to the state manifest only if the node "isn't among the selected nodes, and it doesn't exist in the database (or `--favor-state` is used)". It needs `--defer` and `--state` (or env vars). Ephemeral models "are never deferred"; multi-parent tests may "run across environments". `DOCUMENTED`
- **`--favor-state`** "prioritizes node definitions from the `--state` directory", except for selected nodes. `DOCUMENTED`
- **`dbt clone`**: "If your data platform supports zero-copy cloning of tables (Snowflake, Databricks, or BigQuery), and this model exists as a table in the source environment, dbt will create it in your target environment as a clone. Otherwise, dbt will create a simple pointer view". It recreates existing relations only with `--full-refresh`. "Unlike deferral, `dbt clone` requires compute and creates additional objects". `DOCUMENTED`
- **Slim CI pattern**: `dbt build -s state:modified+ --defer --state path/to/prod/artifacts`, optionally with `result:error+`, `result:fail+` and `source_status:fresher+`. `DOCUMENTED`
- **Incremental models in CI.** Recommended: `dbt clone --select state:modified+,config.materialized:incremental,state:old`, then `dbt build --select state:modified+` (v1.6+, zero-copy platforms only). Reason: in a new PR schema `is_incremental()` is false, so the model is "built in its entirety ... You're running in full-refresh mode", which costs money and hides failures that only occur on incremental runs. `DOCUMENTED`
- **dbt platform CI jobs.** Default `dbt build --select state:modified+`, deferring to Production; triggered on PR open or push (native GitHub, GitLab, Azure DevOps); temporary schemas prefixed `dbt_cloud_pr_`, auto-dropped only via native Git webhooks. Caveat: the comparison state is the latest successful run in the environment "from any job that updates artifacts there". v2 CI jobs use the built-in `dbt lint`. `DOCUMENTED`
- **Advanced CI "Compare changes"** (Enterprise/Enterprise+) "runs SQL queries in the current CI job's environment to compare the CI model ... to the production model" (primary keys, rows, columns, modified rows); caches ≤100 records per model for up to 30 days; BigQuery, Databricks, Postgres, Redshift, Snowflake, same host only. It does **not** compare cost. `DOCUMENTED`
- **State-aware orchestration** (Enterprise; "now available in dbt v2 (private preview)"): compiled-SQL diffs, upstream data freshness, shared model-level state across jobs, `build_after`. "Efficient testing" (private beta) "is only available in deploy jobs, not in ... CI". `DOCUMENTED`
- **dbt State** (2026). It skips a node when the object exists, its logic is unchanged and it is within `lag_tolerance`; clones from any environment "with identical logic and fresh data" (including a CI schema); otherwise builds, "automatically deferring any unselected upstream nodes". Works with v1 and v2. Pricing is on a separate page (`UNCONFIRMED`). `DOCUMENTED`
- **v2 static analysis.** v2 renders Jinja, then produces "a logical plan for every rendered query". Column-level lineage exists only in `strict` mode, which requires `dbt login`; in `baseline` mode introspective queries use "the remote database as the source of truth — similar to dbt v1". `DOCUMENTED`
- **Implication.** Under dbt State or state-aware orchestration, rebuild frequency depends on data arrival, `lag_tolerance`/`build_after` and cross-environment reuse, not only on the schedule. The "recurring" multiplier is itself a prediction. `INFERRED`

### A3. Artifacts: `manifest.json`, `run_results.json` and `adapter_response`

- **Manifest `v12`** (v1.8–v1.11 and v2.0). Top-level keys: `nodes`, `sources`, `macros`, `exposures`, `metrics`, `groups`, `docs`, `parent_map`, `child_map`, `group_map`, `selectors`, `disabled`; `unique_id` = `<resource_type>.<package>.<name>`. `DOCUMENTED`. The v12 schema's `Model` node includes `unique_id`, `raw_code`, `compiled`, `compiled_code`, `checksum` (`FileHash{name, checksum}`), `depends_on{macros[], nodes[]}`, `config` (`ModelConfig` incl. `materialized`, `incremental_strategy`, `event_time`, `batch_size`, `lookback`), `unrendered_config`, `relation_name`, `defer_relation`, `contract`, `language`, `refs`, `sources`, `extra_ctes`. `DOCUMENTED` (schema). `compiled_code` exists only for compiled nodes, so a `dbt parse`-only manifest lacks it. `INFERRED`
- **run_results `v6`.** Per result: `unique_id`, `status`, `timing` (compile/execute), `thread_id`, `execution_time`, `adapter_response`, `message`, `failures`, `compiled`, `compiled_code`, `relation_name`. `adapter_response` "varies by adapter. For example, success `code`, number of `rows_affected`, total `bytes_processed`... Not applicable for data tests." `DOCUMENTED`

| Adapter (source branch) | `adapter_response` fields | Cost primitive (project classification) |
|---|---|---|
| base (`dbt-adapters` main) | `_message`, `code`, `rows_affected`, `query_id` | `query_id` only if the adapter fills it |
| dbt-bigquery (`dbt-adapters` main) | + `bytes_processed`, `bytes_billed`, `slot_ms`, `job_id`, `location`, `project_id` (from `QueryJob.total_bytes_processed`, `.total_bytes_billed`, `.slot_millis`) | bytes billed: **DIRECTLY_MEASURED** (on-demand $ = bytes × rate); `slot_ms`: DIRECTLY_MEASURED resource, but $ is only **DERIVED** under capacity pricing |
| dbt-snowflake (`dbt-adapters` main) | `query_id` + `rows_inserted/deleted/updated/duplicates` (need snowflake-connector-python ≥ 4.2.0) | **no cost field**; credits are DERIVED by joining `query_id` to account-usage views |
| dbt-databricks (`databricks/dbt-databricks` main) | `query_id` (or "N/A"); `job_id`/`job_run_id`/`task_run_id` filled "only when dbt runs as a `dbt_task`" | **no cost field**; DBUs are DERIVED from system tables |
| dbt-redshift (`dbt-adapters` main) | plain `AdapterResponse(_message="SUCCESS", rows_affected)`; `query_id` not populated | **no cost field and no id**; match via comments or `query_group` |

All rows: `DOCUMENTED-SRC`.
- Only BigQuery exposes cost-relevant statistics directly in dbt artifacts. On Snowflake and Databricks, Cost CI must join a query id to warehouse metadata, adding latency (Snowflake `QUERY_ATTRIBUTION_HISTORY`: "Up to eight hours"). `DOCUMENTED` / `INFERRED`
- `UNCONFIRMED`: whether `adapter_response` covers *all* statements of a multi-statement materialization (temp tables, partition discovery, merge, `OPTIMIZE`, metadata queries) or only the main one. Do not assume it sums a model's cost.
- dbt-bigquery's `connections.dry_run(sql)` is used by `BigQueryAdapter.validate_sql`, which is **not** `@available`, so Jinja cannot call it. `DOCUMENTED-SRC`. The v2 changelog notes adapter_response support and "[BigQuery] Support getting query_id in AdapterResponse"; whether v2 still returns `bytes_billed`/`slot_ms` is `UNCONFIRMED`.
- **CI runs are poor cost samples.** `--empty` "limits the refs and sources to zero rows" (run, build, snapshot, compile; seed from 1.12); source is the docs page as shown in search results, not fetched. `--sample` time-filters refs/sources for run and build and is ignored for Python models. `DOCUMENTED`. PR schemas also build the full-refresh branch (A5). `INFERRED`

### A4. Query attribution from dbt

- **Default `query-comment`**: `/* {"app": "dbt", "dbt_version": ..., "profile_name": ..., "target_name": ..., "node_id": "model.<pkg>.<name>"} */`. Keys: `comment` (string or macro, may take `node`), `append` (default `false`), `job-label` (BigQuery only). On Snowflake "the comment appears at the end of the query" because Snowflake strips leading comments; `null` disables it. `DOCUMENTED`
- **BigQuery.** `query-comment: {job-label: true}` adds the comment's dict items "as job labels on the query it executes", on top of the `labels` config. `DOCUMENTED`. The adapter always adds a `dbt_invocation_id` label, sanitises label values, and reads per-model `reservation` and `priority` into job params. `DOCUMENTED-SRC`
- **Snowflake.** `query_tag` can be set in the profile or per model/folder; dbt runs `alter session set query_tag` at the start of a materialization and resets it at the end, so "build failures midway through a materialization may result in subsequent queries running with an incorrect tag". Override the `set_query_tag` macro to customise. `DOCUMENTED`. SELECT recommends query comments over tags for dbt metadata because of the query-tag length limit (vendor docs).
- **Databricks** (dbt-databricks ≥ 1.11; Databricks query tags are Public Preview). Reserved default tags `@@dbt_model_name`, `@@dbt_core_version`, `@@dbt_databricks_version`, `@@dbt_materialized`; connection- and model-level tags; at most 20 tags, values ≤128 characters. Tags land in `system.query.history.query_tags` and are "supported for Databricks SQL workloads only" (Databricks docs), so Python and job-cluster compute is not covered. `DOCUMENTED`
- **Redshift**: the `query_group` credential ("Query group for WLM and query logging (appears in STL_QUERY, SVL_QLOG, etc.)"). `DOCUMENTED-SRC`. dbt's own Cost Insights on Redshift attributes cost "using the comments it automatically injects". `DOCUMENTED`
- **Compute routing is a config change.** `snowflake_warehouse` (per model or test), `databricks_compute` (per model) and BigQuery `reservation` (per model). `DOCUMENTED` / `DOCUMENTED-SRC`. A PR that moves a model to a bigger warehouse changes $ without any SQL change; `state:modified.configs` catches it. `INFERRED`

### A5. Incremental models

- **`is_incremental()` source** (`dbt-adapters` global project). Returns `False` when `not execute` (parse time). Otherwise it calls `adapter.get_relation(this.database, this.schema, this.table)` and returns true only if the relation is not none, its type is `table`, `materialized == 'incremental'`, and `not should_full_refresh()`. `DOCUMENTED-SRC`. The docs list the same three conditions. `DOCUMENTED`
- **`dbt compile` needs a connection**: it "needs a data platform connection in order to gather the info it needs (including from introspective queries)", including the relation cache that tells it "whether an incremental model already exists". `--no-introspect` errors on nodes that need introspection. `DOCUMENTED`. So compiled SQL for an incremental model depends on the target compiled against: the full-refresh branch in a fresh PR schema, the incremental branch with clone or prod. `INFERRED` from the source plus the clone-incremental page. Whether `--defer` changes how `{{ this }}` resolves is `UNCONFIRMED`.

Supported strategies per adapter, from the docs table (raw markdown source, v1 Latest/Fusion). `DOCUMENTED`:

| Adapter | append | merge | delete+insert | insert_overwrite | microbatch |
|---|---|---|---|---|---|
| bigquery | – | ✓ | – | ✓ | ✓ |
| snowflake | ✓ | ✓ | ✓ | ✓ (truncate+insert of the *whole* table) | ✓ |
| databricks (+ `replace_where`) | ✓ | ✓ | ✓ | ✓ | ✓ |
| redshift / postgres / trino / fabric / teradata / duckdb | ✓ | ✓ | ✓ | – | ✓ |
| spark / athena | ✓ | ✓ | – | ✓ | ✓ |
| clickhouse | ✓ | – | ✓ | ✓ | – |

- **Cost notes** (`DOCUMENTED`):
  - BigQuery `merge` "requires scanning all source tables referenced in the model SQL, as well as destination tables. This can be slow and expensive".
  - BigQuery `insert_overwrite`: dynamic partitions run extra discovery queries; static partitions "reduce costs"; `copy_partitions` uses the copy API, which "does not incur any costs for inserting the data".
  - Databricks `liquid_clustered_by` "issues an `OPTIMIZE` ... after each run".
  - `on_schema_change: sync_all_columns` on BigQuery: a column-type change "requires a full table scan".
  - `--full-refresh` drops and rebuilds; the `full_refresh` config overrides the flag.
- **Microbatch** (v1.9+). `DOCUMENTED`
  - Configs: required `event_time`, `begin`, `batch_size` (hour/day/month/year); `lookback` default `1`; optional `concurrent_batches`.
  - "One query per batch"; upstream refs/sources that define `event_time` are filtered automatically, and "If your upstream models don't have `event_time` configured, dbt cannot automatically filter them ... and will perform full table scans on every batch run."
  - Backfills via `--event-time-start`/`--event-time-end`; `dbt retry` reruns only failed batches.
  - Underlying strategy: Snowflake and Redshift delete+insert; BigQuery and Spark insert_overwrite; Databricks replace_where; Postgres merge.
- `INFERRED`: steady-state microbatch cost ≈ (lookback+1) batches × cost per batch × runs. A PR that removes `event_time` from an *upstream* model turns downstream batch reads into full scans: a cost change in a node the PR did not touch.
- **Recurring cost outside dbt** (`DOCUMENTED`): Snowflake dynamic tables (with `target_lag`, "Snowflake manages refreshes automatically"; `refresh_warehouse` since dbt-snowflake 1.11); BigQuery materialized views auto-refresh "within 5 minutes of changes in the base table, but not more frequently than once every 30 minutes"; Snowflake `cluster_by` runs `alter table ... cluster by` and "Automatic clustering is enabled by default" (serverless; `QUERY_ATTRIBUTION_HISTORY` excludes "Costs for serverless features", Snowflake docs). None of these costs appear in dbt `run_results`. `INFERRED`

### A6. Python models

- **Supported platforms and cost.** Snowflake, BigQuery and Databricks, including in v2. "All Python code is executed remotely on the platform"; "the cloud resources that run them can be more expensive ... That compute might sometimes live on a separate service". `dbt.config()` accepts "only literal values" because it is parsed statically. `DOCUMENTED`
- **Snowflake.** Runs as an anonymous stored procedure (`WITH <proc> AS PROCEDURE ... LANGUAGE PYTHON ... EXECUTE AS CALLER ... CALL <proc>()`) on the session's warehouse. `DOCUMENTED-SRC`. Packages come from Anaconda. `DOCUMENTED`
- **Databricks.** `submission_method`: `all_purpose_cluster` (default; Command API or notebook), `job_cluster` (spins a cluster up and down per model; needs `job_cluster_config`), `serverless_cluster`, `workflow_job` (persistent workflow). `databricks_compute` chooses compute only for the model's SQL; the Python runs on an all-purpose or serverless cluster. `DOCUMENTED`
- **BigQuery.** `submission_method` is `bigframes` (Colab runtime), `serverless` (Dataproc Serverless) or `cluster` (Dataproc cluster). `DOCUMENTED`
- **Attribution.** Python compute on Databricks job clusters and on Dataproc is billed outside SQL query history, and Databricks query tags cover SQL warehouses only; Cost CI would need job or cloud billing sources. `INFERRED`

---
## Part B — Prior art

### B7. Tools that estimate the cost of changes pre-merge (or claim to)

**Infrastructure-as-code (the design reference)**
- **Infracost** (Apache 2.0; Terraform/Terragrunt, CloudFormation, AWS CDK; AWS, Azure, Google). `DOCUMENTED` (docs, README)
  - Mechanism: "parses Terraform HCL code directly to extract only cost-related parameters", prices come "from an internal Cloud Pricing API", no cloud credentials needed, "over 1,100" Terraform resources. PR comments show "the cost diff, FinOps policy violations, and tagging issues".
  - Usage-based costs are assumptions: "we've predefined values that attempt to set each usage-based cost as $5/month for common configurations", overridable via Infracost Cloud usage defaults or `infracost-usage.yml` (repo file wins); disabling them hides those costs. No doc describes pulling actual usage from cloud accounts (`UNCONFIRMED` absence).
  - Explicitly **not** estimated: it "applies public on-demand list prices by default, so Reserved Instances, Savings Plans, committed use discounts, negotiated enterprise agreements, and account-wide free tiers are not reflected unless they are modeled explicitly" (custom price books). Accuracy: "Fixed-price resources such as AWS EC2 instances estimate closely, while usage-based resources such as AWS Lambda and Amazon S3 are only as accurate as the usage values provided".
  - BigQuery: only `google_bigquery_dataset`/`google_bigquery_table` are priced; jobs and routines are "free"; no Snowflake or Databricks provider resources are listed.
- **HCP Terraform cost estimation**: "hourly and monthly cost ... along with the monthly delta" for AWS, GCP, Azure; off by default; "some resources don't have cost information available or have unpredictable usage-based pricing". `DOCUMENTED`
- **Kubecost `cost-prediction-action`** predicts Kubernetes manifest cost in CI: environment-specific (history-informed) with a Kubecost API URL, default pricing without; "Manifests without container resource requests will not produce predictions". The closest analogue of history-informed prediction. `DOCUMENTED` (README)

**dbt and warehouse tools**

| Tool | What it claims or does | Mechanism | Pre-merge? | Evidence |
|---|---|---|---|---|
| **dbt-costgate** (PyPI v1.1.0, 2026-07-31, Apache-2.0; GitHub showed 0 stars and 256 commits at fetch) | "Dry-run what changed, price the diff, and catch the $500-a-day model before it merges" | `state:modified` against the prod manifest (git-diff fallback); compiles both versions; BigQuery `dryRun` bytes × region-aware on-demand rate, optionally × run frequency; sticky PR comment, JSON, exit code on $ / % / TiB thresholds; incremental rows shown as a "ceiling rather than the nightly bill"; notes that under Editions "bytes scanned is a proxy signal" | **Yes, BigQuery only** | README/PyPI: `CLAIMED`. The only direct match found; negligible adoption signal |
| **dbt platform Cost Insights** (Enterprise) | "estimated costs and compute time for your dbt projects and models" | Warehouse usage metadata, computed daily (~17:00 UTC) over the last 7 days. Snowflake: attribution views. BigQuery: `information_schema.jobs`. Databricks: "Proportionally allocates DBUs based on query runtime". Redshift (Preview): comments. Reduction formula `average_cost_per_build * reuse_count`. States "*not* forecasts" and "directionally accurate" | **No**: production and staging only; CI not mentioned | `DOCUMENTED` |
| dbt Advanced CI (Compare changes) | Data diff between CI and prod models | Warehouse SQL; results cached | Yes, but for data, not cost | `DOCUMENTED` |
| Datafold CI | Value-level data diff plus downstream impact in a PR comment | Queries the warehouse; column lineage | Yes, but no cost estimate | `DOCUMENTED` |
| Recce | Schema, row-count and data diffs plus "impact radius" for dbt PRs | Warehouse queries | Yes, but no cost estimate | `DOCUMENTED` |
| SELECT (plus OSS `dbt-snowflake-monitoring`) | dbt spend "by project, target, materialization and resource type" | Query tags and comment metadata joined to query history | No PR feature found | `DOCUMENTED` (docs) |
| Tobiko Cloud (SQLMesh) | "tracks data warehouse cost estimates per model" (BigQuery on-demand, Snowflake credits) plus savings from prevented reruns | Method not documented | No pre-plan estimate documented (`UNCONFIRMED`) | `DOCUMENTED` / `CLAIMED` |
| Unravel CI/CD (Databricks, Snowflake) | At PR time, "AI-powered checks to ensure the code is performant and efficient" | **Not documented** on the pages read (static analysis? a test run?) | Claims yes | `CLAIMED` |
| Monte Carlo Performance | "Get alerted when query costs or credit usage goes up" | Query history | No (post-hoc) | `CLAIMED` / `DOCUMENTED` |
| Datadog (Data Observability; CCM) | Job and cluster cost visibility. CCM BigQuery allocation: on-demand = "bytes processed"; reservations = `(query_slot_usage / total_slot_usage) * total_project_reservation_cost`, remainder marked `cluster_idle` | Billing plus job metadata | No (post-hoc) | `DOCUMENTED` |
| Paradime Radar, Synq, Metaplane (now "by Datadog"), Alvin | Cost monitoring (Paradime, `CLAIMED` "20%+" savings) or lineage/impact analysis in PRs (Synq, Alvin) | Post-hoc cost or lineage | No PR cost estimate found | Search-level only: `UNCONFIRMED` |

**Native warehouse capabilities relevant to pre-merge estimation** (all `DOCUMENTED`)
- **BigQuery dry run** returns the bytes a query will process, at no cost. The estimate "can be higher than the actual number of bytes billed" (upper bound for clustered tables; ignores the cache; row-level security returns 0 bytes). Under capacity pricing, "It's not possible to estimate the exact cost of an individual query before execution with precise accuracy".
- **Snowflake `EXPLAIN`** returns `partitionsTotal`/`partitionsAssigned`/`bytesAssigned` without a running warehouse (compilation uses cloud-services credits); "assignedPartitions and assignedBytes values are upper bound estimates"; no cost or time estimate.
- **Snowflake feature estimators.** `SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_COSTS` gives a one-off upper bound plus daily maintenance based on 7 days of DML: "actual realized costs can vary by up to 100% (or, in rare cases, several times)". Search-optimization and QAS estimators also exist. No general pre-execution query cost estimator was found (`UNCONFIRMED` absence).
- **Snowflake `QUERY_ATTRIBUTION_HISTORY`**: `CREDITS_ATTRIBUTED_COMPUTE` per query; excludes warehouse idle time, cloud services, storage, transfer and serverless features; queries ≤ ~100 ms excluded; latency up to 8 h; retention 365 days.
- **Databricks query tags** land in `system.query.history`. No pre-execution cost estimator was found (`UNCONFIRMED`).

### B8. Research on predicting query cost or runtime (evidence on accuracy)

1. **Wu et al., "Stage: Query Execution Time Prediction in Amazon Redshift"** (arXiv:2403.02286, 2024). Exec-time cache, local model and global model, evaluated on 27.4M queries from the 100 most-billed instances. Overall absolute error: MAE 7.76 s, P50 0.67 s (AutoWLM baseline 17.87 / 2.03 s). For queries of **300 s or more**: MAE 744 s, P50 236 s, P90 1,496 s. 61.8% of queries were exact repeats, yet the cache "does make significant errors ... because these repeating queries are executed at different system loads, buffer pool states, and concurrency conditions". Relevance: error concentrates in the long queries that dominate cost, and even exact repeats vary. `DOCUMENTED`
2. **van Renen et al., "Why TPC Is Not Enough: An Analysis of the Amazon Redshift Fleet"** (PVLDB 17(11), 2024; Redset). "in 50% of database clusters 80% of queries are 1-to-1 repetitions of previously seen queries"; also write-heavy pipelines, frequent repeating CTAS, and long tails (median runtime 100 ms, maximum several days). Relevance: recurring pipelines make history-anchored estimation plausible. `DOCUMENTED`
3. **Siddiqui et al., "Cost Models for Big Data Query Processing: Learning, Retrofitting, and Our Findings"** (SIGMOD 2020, Microsoft SCOPE, "Cleo"). Models learned on recurring subexpressions were "2 to 3 orders of magnitude more accurate, and 20X more correlated with the actual runtimes" than the default cost model. Relevance: optimizer cost units are poor proxies; models trained on workload history work much better. `DOCUMENTED`
4. **Leis et al., "How Good Are Query Optimizers, Really?"** (PVLDB 9(3), 2015): cardinality "estimators routinely produce large errors". Relevance: static estimates built from plan statistics inherit those errors. `DOCUMENTED`
5. **Heinrich et al., "How Good are Learned Cost Models, Really?"** (SIGMOD 2025). Seven learned models vs a traditional one: "the traditional model often still outperforms LCMs" on optimization tasks. Relevance: better average accuracy does not guarantee correct plan comparisons, which is exactly Cost CI's A/B question. `DOCUMENTED`
6. **Hilprecht & Binnig, "Zero-Shot Cost Models"** (arXiv:2201.00561, 2022). A pre-trained model transfers to unseen databases "without requiring any query executions", with few-shot refinement. Relevance: cold start for new models (`state:new`). `DOCUMENTED`
7. **Pathak, "Pre-Execution Query Slot-Time Prediction in Cloud Data Warehouses"** (arXiv:2604.20145, April 2026 preprint; single author; ~1.5k queries). BigQuery slot-time: 74% explained variance overall and a 30–37% MAE reduction vs mean/median baselines on cost-relevant queries, but on queries of 20 minutes or more "the model does not outperform trivial baselines". Relevance: pre-execution slot estimation remains weak where the money is. `DOCUMENTED` (not peer-reviewed)
8. **Song et al., "Evaluating Learned Query Performance Prediction Models at LinkedIn"** (arXiv:2504.17181, 2025; Trino). Notes models are "predominantly validated using synthetic datasets" and tests them on production OLAP queries, including CPU-time prediction. Relevance: benchmark accuracy does not carry over to production. `DOCUMENTED` (abstract)
- **Context, not evidence**: Szlang et al. (PVLDB 18(12), 2025) studied 667M Snowflake queries but "deliberately excluded ... ETL or data engineering", so it says nothing about dbt workloads. `DOCUMENTED`

### B9. What the prior art implies: commodity vs hard

**Commodity** (documented primitives or existing products; little differentiation)
- **Change sets and lineage**: `state:modified+`, `parent_map`/`child_map`, `dbt ls`; column lineage from v2 (strict mode), Datafold, Recce, Paradime. (A1, A3)
- **Historical per-model cost attribution**: comments, tags and labels joined to warehouse metadata. At least six products do this post-hoc (dbt Cost Insights, SELECT, Datadog, Monte Carlo, Tobiko, Paradime).
- **BigQuery on-demand bytes before a run**: a free API, already packaged as an OSS PR gate (dbt-costgate).
- **PR comment and threshold-gate UX** (Infracost, Kubecost, dbt-costgate), and price tables with customer overrides (Infracost custom price books, dbt Cost Insights pricing variables).

**Hard** (no documented solution, and the evidence points to difficulty)
1. **Forecasting compute on time-billed engines** (Snowflake credits, Databricks DBUs, BigQuery Editions slots). No vendor gives a general pre-execution estimate: Snowflake `EXPLAIN` gives only upper-bound bytes, and BigQuery says capacity cost cannot be estimated precisely. Research puts the largest errors in long queries (Stage: P50 error 236 s at 300 s or more; the BigQuery preprint no better than trivial baselines at 20 minutes or more). Anchoring on each model's own production history is the only approach with support (Cleo, Redset, Stage's cache), and even that varies for identical queries. `INFERRED`
2. **Incremental steady state vs the CI build.** CI compiles and runs the full-refresh branch (A5); recurring cost is the incremental branch × data arriving per run. The only direct prior art punts ("read this as the ceiling").
3. **The recurring multiplier** needs orchestration metadata, and under dbt State or state-aware orchestration rebuilds depend on data (A2).
4. **Marginal vs attributed $ on shared or prepaid capacity.** Snowflake attribution excludes idle time; Datadog books unallocated reservation cost as `cluster_idle`; dbt calls its numbers "directionally accurate". A PR's "incremental $" depends on how it is defined: that definition is the product decision, not plumbing. `INFERRED`
5. **Config-triggered costs invisible to query attribution**: auto-clustering (whose own estimator can be off by 100% or more), dynamic table and materialized view refreshes, `OPTIMIZE` after liquid clustering, Python on job clusters or Dataproc. (A5, A6)
6. **Detecting the change at all**: var, env and target values, data-dependent SQL, `event_time` edits upstream (A1, A5). Requires rendered-SQL diffs of both sides and a warehouse connection at compile time.
7. **Downstream and consumer effects** (BI queries on a table whose partitioning or clustering changed), outside dbt and outside every tool surveyed.

**Net.** Infracost succeeds by pricing *fixed-price* resources deterministically and treating usage as a user-supplied assumption. Warehouse compute is almost entirely usage-based, so the Infracost model maps well only to BigQuery on-demand (via dry run). Elsewhere, the value lies in the history-anchored forecast and its calibration, which no surveyed tool documents. The dbt platform already holds the ingredients (CI jobs, rendered-SQL hashing in dbt State, Cost Insights history), so a first-party entry is a platform risk. `INFERRED`

### B10. Open questions

1. What share of target users run BigQuery **on-demand**, the only regime where dry-run bytes ≈ the bill? `UNCONFIRMED`
2. Does a ratio estimator hold up empirically, e.g. production cost of model M × (new/old dry-run bytes or new/old `EXPLAIN bytesAssigned`)? The research tail errors suggest it fails for joins, spills and skew; this needs measurement (project hypotheses HA/HB).
3. How can CI faithfully produce the **incremental branch** and microbatch `lookback` windows (clone the prod relation on zero-copy platforms, or compile against prod metadata)? Does `--defer` affect `{{ this }}`? `UNCONFIRMED`
4. Which statements does `adapter_response` represent for multi-statement materializations? `UNCONFIRMED`
5. How do we obtain production run frequency and actual rebuild counts (dbt platform APIs, orchestrator configs, dbt State reuse)? What is the error in the recurring multiplier itself?
6. Should Cost CI report attributed or marginal $, especially on shared warehouses and reservations? (HC/HD)
7. What is the cold start for `state:new` models with no history? Zero-shot models are research-grade; is there a heuristic fallback, and what error does it carry?
8. Can v2's logical plans and column lineage be consumed offline from artifacts (the "dbt Information Schema" parquet), and under what auth (strict mode requires `dbt login`) and license? `UNCONFIRMED`
9. What accuracy bar changes a merge decision: order-of-magnitude flags, or ±X%? No surveyed tool publishes accuracy for its own estimates.
10. Will dbt Labs ship pre-merge cost estimates in CI jobs? It already owns the necessary pieces. `UNCONFIRMED`

### 11. Sources (all fetched 2026-09-28)

**dbt docs** (all under `https://docs.getdbt.com`):
- Node selection: `/reference/node-selection/methods`, `/reference/node-selection/state-comparison-caveats`, `/reference/node-selection/state-selection`, `/reference/node-selection/configure-state`, `/reference/node-selection/defer`, `/reference/node-selection/graph-operators`
- Commands and flags: `/reference/commands/clone`, `/reference/commands/compile`, `/reference/global-configs/behavior-flags/state_modified_compare_more_unrendered_values`, `/reference/global-configs/behavior-changes`
- Deploy and CI: `/docs/deploy/ci-jobs`, `/docs/deploy/advanced-ci`, `/docs/deploy/state-aware-about`, `/docs/deploy/dbt-state-about`, `/best-practices/best-practice-workflows`, `/best-practices/clone-incremental-models`
- v2 / Fusion: `/docs/fusion/new-concepts`, `/docs/fusion/supported-features`, `/blog/dbt-v2-is-ga`, `/docs/dbt-versions/core-upgrade/upgrading-to-v2`
- Artifacts and attribution: `/reference/artifacts/manifest-json`, `/reference/artifacts/run-results-json`, `/reference/project-configs/query-comment`
- Adapter configs: `/reference/resource-configs/snowflake-configs`, `/reference/resource-configs/bigquery-configs`, `/reference/resource-configs/databricks-configs`
- Build: `/docs/build/incremental-models`, `/docs/build/incremental-strategy`, `/docs/build/incremental-microbatch`, `/docs/build/python-models`, `/docs/build/sample-flag`, `/docs/build/empty-flag` (search-result excerpt only)
- Cost: `/docs/explore/cost-insights`, `/docs/explore/explore-cost-data`

**dbt schema and source**
- https://schemas.getdbt.com/dbt/manifest/v12.json
- https://github.com/dbt-labs/dbt-core (README notice); https://github.com/dbt-labs/dbt-core/issues/4304
- https://raw.githubusercontent.com/dbt-labs/dbt-core/1.latest/core/dbt/graph/selector_methods.py
- https://raw.githubusercontent.com/dbt-labs/dbt-core/1.latest/core/dbt/contracts/graph/nodes.py
- https://raw.githubusercontent.com/dbt-labs/dbt-fusion/main/CHANGELOG.md
- https://raw.githubusercontent.com/dbt-labs/docs.getdbt.com/current/website/docs/docs/build/incremental-strategy.md
- `https://raw.githubusercontent.com/dbt-labs/dbt-adapters/main/` + `dbt-adapters/src/dbt/adapters/contracts/connection.py`, `dbt-adapters/src/dbt/include/global_project/macros/materializations/models/incremental/is_incremental.sql`, `dbt-bigquery/src/dbt/adapters/bigquery/connections.py`, `dbt-bigquery/src/dbt/adapters/bigquery/impl.py`, `dbt-snowflake/src/dbt/adapters/snowflake/connections.py`, `dbt-snowflake/src/dbt/adapters/snowflake/adapter_response.py`, `dbt-snowflake/src/dbt/adapters/snowflake/impl.py`, `dbt-redshift/src/dbt/adapters/redshift/connections.py`
- https://raw.githubusercontent.com/databricks/dbt-databricks/main/dbt/adapters/databricks/connections.py and `.../handle.py`; https://github.com/databricks/dbt-databricks/issues/279
- https://github.com/dbt-labs/summit-2026-operationalize-cost-visibility-in-dbt (Snowflake workshop repo; no CI cost gate)

**Warehouse docs**
- https://docs.cloud.google.com/bigquery/docs/best-practices-costs
- https://docs.snowflake.com/en/sql-reference/sql/explain
- https://docs.snowflake.com/en/sql-reference/account-usage/query_attribution_history
- https://docs.snowflake.com/en/sql-reference/functions/system_estimate_automatic_clustering_costs
- https://docs.databricks.com/aws/en/sql/user/queries/query-tags

**Prior-art tools**
- Infracost: https://www.infracost.io/docs/ · https://www.infracost.io/docs/faq/ · https://www.infracost.io/docs/features/usage_based_resources/ · https://www.infracost.io/docs/supported_resources/overview/ · https://www.infracost.io/docs/supported_resources/google/ · https://www.infracost.io/resources/glossary/terraform-cost-estimation · https://github.com/infracost/infracost
- HCP Terraform: https://developer.hashicorp.com/terraform/cloud-docs/cost-estimation · Kubecost: https://github.com/kubecost/cost-prediction-action
- dbt-costgate: https://pypi.org/project/dbt-costgate/ · https://github.com/Drichards124/dbt-costgate
- SELECT: https://select.dev/docs/dbt · Recce: https://docs.reccehq.com/ · Datafold: https://docs.datafold.com/deployment-testing/how-it-works · Tobiko: https://sqlmesh.readthedocs.io/en/stable/cloud/features/costs_savings/
- Unravel: https://www.unraveldata.com/resources/unravel-cicd-integration-for-databricks/ · https://www.unraveldata.com/resources/unravel-cicd-integration-for-snowflake
- Monte Carlo: https://montecarlo.ai/performance-monitoring · Datadog: https://www.datadoghq.com/products/observability/data-observability/ · https://docs.datadoghq.com/cloud_cost_management/allocation/bigquery/
- Search-level only (not fetched): https://www.paradime.io/paradime-radar-bigquery-cost-optimization · https://www.synq.io/integrations/dbt · https://www.metaplane.dev/ · https://medium.com/alvin-ai/data-lineage-and-impact-analysis-with-alvin-and-dbt-1632d3b17174

**Papers**
- Stage: https://arxiv.org/abs/2403.02286 (plus PDF) · Redset: https://www.vldb.org/pvldb/vol17/p3694-saxena.pdf · Cleo: https://arxiv.org/abs/2002.12393
- Leis et al.: https://www.vldb.org/pvldb/vol9/p204-leis.pdf · Heinrich et al.: https://arxiv.org/abs/2502.01229 · Zero-shot: https://arxiv.org/abs/2201.00561
- BigQuery slot-time preprint: https://arxiv.org/abs/2604.20145 · LinkedIn QPP: https://arxiv.org/abs/2504.17181 · Snowflake workload study: https://www.vldb.org/pvldb/vol18/p5126-bress.pdf
