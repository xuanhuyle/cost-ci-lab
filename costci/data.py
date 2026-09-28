"""Generate the lab's data environments.

prod        TPC-H at scale factor SF, facts physically clustered by date (so zone-map pruning is
            meaningful, like micro-partition / partition pruning on a warehouse).
CI samples  what a team could plausibly use instead of a full production clone:
  bern01    naive 1% Bernoulli sample of every large table independently (TABLESAMPLE-style)
  key01     key-consistent 1% sample on the customer hierarchy (customer -> orders -> lineitems);
            dimension tables kept whole
  key10     same, 10%
  recent90  every fact table filtered on its own date column to the last 90 days (a common dbt
            "limit data in CI" pattern); dimensions kept whole

Usage:  python -m costci.data --sf 2
"""
from __future__ import annotations

import argparse
import json
import shutil
import time

import duckdb

from .paths import CATALOG, DATA, MEMORY_LIMIT, env_db

RUN_DATE = "1998-08-02"   # lab "today"; also the dbt var run_date default
SEED = 42
FACTS = ["lineitem", "orders"]
TABLES = ["lineitem", "orders", "customer", "part", "partsupp", "supplier", "nation", "region"]


def _connect(env: str, fresh: bool = False) -> duckdb.DuckDBPyConnection:
    path = env_db(env)
    if fresh and path.parent.exists():
        shutil.rmtree(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute(f"SET temp_directory='{(DATA / 'spill').as_posix()}'")
    return con


def build_prod(sf: float) -> None:
    con = _connect("prod", fresh=True)
    con.execute("INSTALL tpch; LOAD tpch;")
    con.execute("CREATE SCHEMA gen")
    con.execute(f"CALL dbgen(sf={sf}, schema='gen')")
    con.execute("CREATE SCHEMA raw")
    order_by = {"lineitem": "l_shipdate, l_orderkey", "orders": "o_orderdate, o_orderkey"}
    for t in TABLES:
        ob = f" ORDER BY {order_by[t]}" if t in order_by else ""
        con.execute(f"CREATE TABLE raw.{t} AS SELECT * FROM gen.{t}{ob}")
    con.execute("DROP SCHEMA gen CASCADE")
    con.execute("CHECKPOINT")
    con.close()


def _copy_from_prod(env: str, table_sql: dict[str, str]) -> None:
    con = _connect(env, fresh=True)
    con.execute(f"ATTACH '{env_db('prod').as_posix()}' AS src (READ_ONLY)")
    con.execute("CREATE SCHEMA raw")
    for t in TABLES:
        sql = table_sql.get(t, f"SELECT * FROM src.raw.{t}")
        con.execute(f"CREATE TABLE raw.{t} AS {sql}")
    con.execute("DETACH src")
    con.execute("CHECKPOINT")
    con.close()


def build_bernoulli(env: str, pct: float) -> None:
    order_by = {"lineitem": "l_shipdate, l_orderkey", "orders": "o_orderdate, o_orderkey"}
    sql = {}
    for t in ["lineitem", "orders", "customer", "part", "partsupp", "supplier"]:
        ob = f" ORDER BY {order_by[t]}" if t in order_by else ""
        sql[t] = (f"SELECT * FROM (SELECT * FROM src.raw.{t} "
                  f"USING SAMPLE {pct}% (bernoulli, {SEED})){ob}")
    _copy_from_prod(env, sql)


def build_key_consistent(env: str, per_mille: int) -> None:
    keep = f"hash(c_custkey) % 1000 < {per_mille}"
    sql = {
        "customer": f"SELECT * FROM src.raw.customer WHERE {keep}",
        "orders": (f"SELECT o.* FROM src.raw.orders o WHERE o.o_custkey IN "
                   f"(SELECT c_custkey FROM src.raw.customer WHERE {keep}) "
                   f"ORDER BY o_orderdate, o_orderkey"),
        "lineitem": (f"SELECT l.* FROM src.raw.lineitem l WHERE l.l_orderkey IN "
                     f"(SELECT o_orderkey FROM src.raw.orders WHERE o_custkey IN "
                     f"(SELECT c_custkey FROM src.raw.customer WHERE {keep})) "
                     f"ORDER BY l_shipdate, l_orderkey"),
    }
    _copy_from_prod(env, sql)


def build_recent(env: str, days: int) -> None:
    cutoff = f"DATE '{RUN_DATE}' - INTERVAL {days} DAY"
    sql = {
        "orders": f"SELECT * FROM src.raw.orders WHERE o_orderdate > {cutoff} ORDER BY o_orderdate, o_orderkey",
        "lineitem": f"SELECT * FROM src.raw.lineitem WHERE l_shipdate > {cutoff} ORDER BY l_shipdate, l_orderkey",
    }
    _copy_from_prod(env, sql)


def describe(env: str) -> dict:
    con = duckdb.connect(str(env_db(env)), read_only=True)
    rows = {t: con.execute(f"SELECT count(*) FROM raw.{t}").fetchone()[0] for t in TABLES}
    con.close()
    return {"env": env, "rows": rows, "db_bytes": env_db(env).stat().st_size}


SAMPLE_BUILDERS = {
    "bern01": lambda: build_bernoulli("bern01", 1),
    "key01": lambda: build_key_consistent("key01", 10),
    "key10": lambda: build_key_consistent("key10", 100),
    "recent90": lambda: build_recent("recent90", 90),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sf", type=float, default=2.0)
    ap.add_argument("--only", nargs="*", help="subset of envs to (re)build")
    args = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    envs = args.only or (["prod"] + list(SAMPLE_BUILDERS))
    summary = {}
    for env in envs:
        t0 = time.perf_counter()
        if env == "prod":
            build_prod(args.sf)
        else:
            SAMPLE_BUILDERS[env]()
        d = describe(env)
        d["build_seconds"] = round(time.perf_counter() - t0, 1)
        summary[env] = d
        print(json.dumps(d))
    meta_path = DATA / "environments.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta.update(summary)
    meta["_sf"] = args.sf if "prod" in envs else meta.get("_sf")
    meta_path.write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
