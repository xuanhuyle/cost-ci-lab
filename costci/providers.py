"""Provider abstraction (revised from the brief's CostProvider) and its portability matrix.

The brief proposed one CostProvider with execute/collect/estimate methods. The evidence
(docs/PLATFORM_FEASIBILITY.md, results) splits it into three platform-specific services and one
platform-independent engine:

  Measurement   run or statically inspect a workload in CI -> native usage units
  Telemetry     production history per workload, run timestamps, pool timelines, consumers
  Billing       the capacity pool's billing function + effective price
  Engine        (platform-independent) change -> workloads -> delta usage -> pool replay -> $

`CAPABILITIES` records, per provider, which documented primitive implements each method, with the
primitive classification from Phase 1. It is data, checked by tests/test_providers.py, so gaps are
explicit rather than hidden inside adapter code. Only the DuckDB lab adapter is executable here;
the others are UNVALIDATED descriptions of how an adapter would be built.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class NativeUsage:
    """One execution of one workload, in the provider's native units."""
    workload: str
    seconds: float                          # engine/warehouse execution time
    units: dict[str, float] = field(default_factory=dict)   # e.g. bytes_billed, slot_ms, dbu, credits
    provenance: str = ""                    # MEASURED | DERIVED | ESTIMATED + source


class Measurement(Protocol):
    def static_signals(self, sql: str) -> dict: ...                          # plan / dry-run
    def run(self, workload, schema: str, tag: str) -> NativeUsage: ...       # controlled execution
    def clone_for_ci(self, relation: str, target_schema: str) -> None: ...   # zero-copy / shallow clone


class Telemetry(Protocol):
    def workload_history(self, workload_key: str, days: int) -> list[NativeUsage]: ...
    def run_timestamps(self, workload_key: str, days: int) -> list[float]: ...
    def consumers(self, relation: str, days: int) -> list[dict]: ...
    def pool_timeline(self, pool: str, start: float, end: float) -> list[dict]: ...


class Billing(Protocol):
    def billing_model(self, pool: str) -> dict: ...                         # kind + parameters
    def effective_price(self, pool: str) -> float | None: ...


METHODS = ["static_signals", "run", "clone_for_ci", "workload_history", "run_timestamps",
           "consumers", "pool_timeline", "billing_model", "effective_price",
           "attributed_cost_per_run"]

# (primitive, classification). Classification per Phase 1: DIRECTLY_MEASURED | DERIVED |
# ESTIMATED | UNAVAILABLE. "config" = must come from customer configuration.
CAPABILITIES: dict[str, dict[str, tuple[str, str]]] = {
    "duckdb_lab": {
        "static_signals": ("EXPLAIN (FORMAT JSON) estimated cardinalities", "ESTIMATED"),
        "run": ("profiled execution (latency, operator CPU, rows scanned)", "DIRECTLY_MEASURED"),
        "clone_for_ci": ("defer to prod schema; CTAS copy of incremental targets", "DERIVED"),
        "workload_history": ("prod-env MAIN reps (results/bench)", "DIRECTLY_MEASURED"),
        "run_timestamps": ("production_context.yaml schedules", "UNAVAILABLE"),
        "consumers": ("production_context.yaml consumers", "UNAVAILABLE"),
        "pool_timeline": ("synthetic month (costci/economics.py)", "ESTIMATED"),
        "billing_model": ("costci/pools.py rules", "DERIVED"),
        "effective_price": ("config", "UNAVAILABLE"),
        "attributed_cost_per_run": ("seconds x rate", "DERIVED"),
    },
    "snowflake": {
        "static_signals": ("EXPLAIN USING JSON: partitionsAssigned/bytesAssigned (upper bounds, no time)", "ESTIMATED"),
        "run": ("dedicated warehouse + QUERY_TAG; INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION execution_time, bytes_scanned (real time)", "DIRECTLY_MEASURED"),
        "clone_for_ci": ("CREATE TABLE ... CLONE (metadata-only; not for shared DBs) / dbt clone", "DIRECTLY_MEASURED"),
        "workload_history": ("ACCOUNT_USAGE.QUERY_HISTORY by query_tag / query_parameterized_hash (45 min)", "DIRECTLY_MEASURED"),
        "run_timestamps": ("QUERY_HISTORY start_time per hash; TASK_HISTORY", "DERIVED"),
        "consumers": ("ACCOUNT_USAGE.ACCESS_HISTORY base_objects_accessed (Enterprise, 3 h)", "DIRECTLY_MEASURED"),
        "pool_timeline": ("QUERY_HISTORY by warehouse + WAREHOUSE_EVENTS_HISTORY + WAREHOUSE_METERING_HISTORY", "DIRECTLY_MEASURED"),
        "billing_model": ("warehouse size/generation/clusters/auto_suspend (SHOW WAREHOUSES) + documented rules", "DERIVED"),
        "effective_price": ("ORGANIZATION_USAGE.RATE_SHEET_DAILY.EFFECTIVE_RATE (org billing role)", "DIRECTLY_MEASURED"),
        "attributed_cost_per_run": ("QUERY_ATTRIBUTION_HISTORY.CREDITS_ATTRIBUTED_COMPUTE (excl. idle; 8 h)", "ESTIMATED"),
    },
    "bigquery": {
        "static_signals": ("dry run totalBytesProcessed (+accuracy flag); no slot estimate", "ESTIMATED"),
        "run": ("job statistics: totalBytesBilled, totalSlotMs, cacheHit; job labels", "DIRECTLY_MEASURED"),
        "clone_for_ci": ("CREATE TABLE ... CLONE (no storage until modified)", "DIRECTLY_MEASURED"),
        "workload_history": ("INFORMATION_SCHEMA.JOBS by label / query_hashes.normalized_literals", "DIRECTLY_MEASURED"),
        "run_timestamps": ("JOBS creation_time per normalized hash", "DERIVED"),
        "consumers": ("JOBS.referenced_tables", "DIRECTLY_MEASURED"),
        "pool_timeline": ("JOBS_TIMELINE + RESERVATIONS_TIMELINE (per-second autoscale)", "DIRECTLY_MEASURED"),
        "billing_model": ("on-demand vs reservation (JOBS.reservation_id) + RESERVATIONS config", "DERIVED"),
        "effective_price": ("billing export cost/credits (~1 day)", "DIRECTLY_MEASURED"),
        "attributed_cost_per_run": ("on-demand: bytes billed x rate (exact); editions: none", "DERIVED"),
    },
    "databricks": {
        "static_signals": ("EXPLAIN COST sizeInBytes/rowCount when stats exist", "ESTIMATED"),
        "run": ("dedicated serverless SQL warehouse + query_tags; Query History API metrics (near real time)", "DIRECTLY_MEASURED"),
        "clone_for_ci": ("SHALLOW CLONE (UC constraints) / dbt clone", "DIRECTLY_MEASURED"),
        "workload_history": ("system.query.history by query_tags @@dbt_model_name (<=1 h)", "DIRECTLY_MEASURED"),
        "run_timestamps": ("system.lakeflow.job_run_timeline; query history", "DERIVED"),
        "consumers": ("system.access.table_lineage (best effort)", "DIRECTLY_MEASURED"),
        "pool_timeline": ("system.compute.warehouse_events + query history", "DERIVED"),
        "billing_model": ("system.compute.warehouses (size, clusters, auto_stop) + DBU/h table", "DERIVED"),
        "effective_price": ("none: list prices only (system.billing.list_prices)", "UNAVAILABLE"),
        "attributed_cost_per_run": ("serverless/job compute: DBUs per job_run_id; SQL warehouse: apportion", "ESTIMATED"),
    },
}
