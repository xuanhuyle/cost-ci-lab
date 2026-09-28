-- Telemetry queries for the live experiment. UNVALIDATED. Column names per docs (2026-09-28).
-- Every experiment statement carries QUERY_TAG = 'costci:<scenario>:<variant>:<env>:<rep>:<workload>'.

-- 1. Real-time per-statement metrics (no latency; 7-day retention) -> the CI measurement
SELECT query_id, query_tag, warehouse_name, warehouse_size, execution_status,
       total_elapsed_time, execution_time, compilation_time, queued_overload_time,
       bytes_scanned, bytes_written, rows_produced
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_WAREHOUSE(
       WAREHOUSE_NAME => 'COSTCI_CI_WH', RESULT_LIMIT => 10000))
WHERE query_tag LIKE 'costci:%';

-- 2. Pruning / spill / cache (ACCOUNT_USAGE, <=45 min latency)
SELECT query_id, query_tag, partitions_scanned, partitions_total, percentage_scanned_from_cache,
       bytes_spilled_to_local_storage, bytes_spilled_to_remote_storage, query_parameterized_hash
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_tag LIKE 'costci:%' AND start_time > DATEADD(day, -3, CURRENT_TIMESTAMP());

-- 3. Snowflake's own per-query attribution (<=8 h latency) vs execution-time measurement
SELECT q.query_tag, SUM(a.credits_attributed_compute) AS credits_attributed,
       SUM(q.execution_time) / 1000 AS exec_s
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY a
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY q ON q.query_id = a.query_id
WHERE q.query_tag LIKE 'costci:%'
GROUP BY 1;

-- 4. What was metered per warehouse-hour (<=3 h): billed uptime incl. idle tail and minimums
SELECT warehouse_name, start_time, credits_used_compute, credits_attributed_compute_queries,
       credits_used_compute - credits_attributed_compute_queries AS idle_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE warehouse_name IN ('COSTCI_CI_WH', 'COSTCI_PROD_WH')
ORDER BY start_time;

-- 5. Resume/suspend events -> validates the pool replay model (costci/pools.py)
SELECT timestamp, warehouse_name, event_name, event_reason, cluster_number, size
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_EVENTS_HISTORY
WHERE warehouse_name IN ('COSTCI_CI_WH', 'COSTCI_PROD_WH')
ORDER BY timestamp;

-- 6. Consumer discovery for a relation (Enterprise edition): which recurring queries read it?
SELECT q.query_parameterized_hash, COUNT(*) AS runs_30d, MEDIAN(q.execution_time) AS median_ms
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
     LATERAL FLATTEN(ah.base_objects_accessed) f
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY q ON q.query_id = ah.query_id
WHERE f.value:"objectName"::string = 'COSTCI_LAB.PROD.DIM_CUSTOMERS'
  AND ah.query_start_time > DATEADD(day, -30, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY runs_30d DESC;
