"""BigQuery control probe (OWNER_REQUEST.md item 2). UNVALIDATED; not run.

Measures, on a real cloud engine and public data only:
  1. dry-run bytes vs billed bytes for MAIN/PR query pairs (native pre-execution estimator)
  2. run-to-run variance of total_slot_ms and elapsed time (noise under capacity-style billing)
  3. how the PR/MAIN ratio of slot-ms compares with the ratio of bytes (bytes != compute)
Safety: refuses to run without --project and --approved; creates no datasets/tables; every job
has maximum_bytes_billed; every query is dry-run first and skipped above --max-gb; results are
not cached (use_query_cache=False) so repeated runs are real executions.

  pip install google-cloud-bigquery
  python live/bigquery/probe.py --project <id> --approved --max-gb 5 --reps 5
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import time
from pathlib import Path

PAIRS = {
    # (MAIN, PR): each pair mimics a benchmark scenario class on public data
    "select_fewer_columns": (
        "SELECT * FROM `bigquery-public-data.thelook_ecommerce.order_items` WHERE status = 'Complete'",
        "SELECT order_id, product_id, sale_price FROM `bigquery-public-data.thelook_ecommerce.order_items` WHERE status = 'Complete'"),
    "add_window_function": (
        "SELECT user_id, SUM(sale_price) s FROM `bigquery-public-data.thelook_ecommerce.order_items` GROUP BY 1",
        "SELECT user_id, SUM(sale_price) s, MAX(r) m FROM (SELECT user_id, sale_price, "
        "RANK() OVER (PARTITION BY user_id ORDER BY created_at) r FROM `bigquery-public-data.thelook_ecommerce.order_items`) GROUP BY 1"),
    "fan_out_join": (
        "SELECT oi.product_id, COUNT(*) c FROM `bigquery-public-data.thelook_ecommerce.order_items` oi GROUP BY 1",
        "SELECT oi.product_id, COUNT(*) c FROM `bigquery-public-data.thelook_ecommerce.order_items` oi "
        "JOIN `bigquery-public-data.thelook_ecommerce.order_items` o2 ON o2.product_id = oi.product_id GROUP BY 1"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--approved", action="store_true", help="owner approval recorded in OWNER_REQUEST.md")
    ap.add_argument("--max-gb", type=float, default=5.0)
    ap.add_argument("--reps", type=int, default=5)
    args = ap.parse_args()
    if not args.approved:
        raise SystemExit("refusing to run without --approved (see docs/OWNER_REQUEST.md item 2)")
    from google.cloud import bigquery  # optional dependency
    client = bigquery.Client(project=args.project)
    cap = int(args.max_gb * 1024 ** 3)
    out = {}
    for name, (main_sql, pr_sql) in PAIRS.items():
        rec = {}
        for variant, sql in (("main", main_sql), ("pr", pr_sql)):
            dry = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
            est = dry.total_bytes_processed
            if est > cap:
                rec[variant] = {"skipped": f"dry run {est} bytes > cap"}
                continue
            runs = []
            for _ in range(args.reps):
                cfg = bigquery.QueryJobConfig(use_query_cache=False, maximum_bytes_billed=cap,
                                              labels={"costci": "probe", "pair": name, "variant": variant})
                job = client.query(sql, job_config=cfg)
                job.result()
                runs.append({"bytes_billed": job.total_bytes_billed, "bytes_processed": job.total_bytes_processed,
                             "slot_ms": job.slot_millis, "elapsed_ms": (job.ended - job.started).total_seconds() * 1000,
                             "cache_hit": job.cache_hit})
                time.sleep(1)
            rec[variant] = {"dry_run_bytes": est, "runs": runs,
                            "slot_ms_cv": st.pstdev([r["slot_ms"] for r in runs]) / st.mean([r["slot_ms"] for r in runs])}
        out[name] = rec
        print(name, json.dumps({v: {k: x for k, x in r.items() if k != "runs"} for v, r in rec.items()}))
    dest = Path(__file__).resolve().parents[2] / "results" / "live" / "bigquery_probe.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
