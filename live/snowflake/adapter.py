"""Snowflake measurement adapter with the same interface as costci.execute.Session.

UNVALIDATED: written against Snowflake docs (2026-09-28) without account access. It exists so the
live run needs credentials, not new code. Requires `pip install -r live/requirements-live.txt`.

Design choices (see docs/PLATFORM_FEASIBILITY.md):
  * dedicated single-cluster warehouses (CI: COSTCI_CI_WH X-Small; prod: COSTCI_PROD_WH Small)
  * USE_CACHED_RESULT = FALSE; every statement tagged via QUERY_TAG
  * per-statement metrics read synchronously from INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION
    (no latency) - never from ACCOUNT_USAGE/billing views, which lag 45 min to 8 h
  * environments are schemas: RAW (SF10 production) and RAW_KEY10 (10% key-consistent sample);
    SQL compiled once by dbt is re-pointed by rewriting schema names (the lab uses the same trick
    with a shared catalog name)
"""
from __future__ import annotations

import json
import os
import re
import time

from costci.execute import Usage

ENV_SCHEMAS = {"prod": {"RAW": "RAW", "PROD": "PROD"},
               "key10": {"RAW": "RAW_KEY10", "PROD": "PROD_KEY10"}}
WAREHOUSES = {"ci": "COSTCI_CI_WH", "prod": "COSTCI_PROD_WH"}


def connect():
    import snowflake.connector  # noqa: WPS433 (optional dependency)
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
        authenticator="SNOWFLAKE_JWT", private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
        role=os.environ.get("SNOWFLAKE_ROLE", "COSTCI_ROLE"), database="COSTCI_LAB")


class SnowflakeSession:
    def __init__(self, env: str, warehouse: str = "ci", tag_prefix: str = "costci"):
        self.env = env
        self.map = ENV_SCHEMAS[env]
        self.con = connect()
        self.cur = self.con.cursor()
        self.tag_prefix = tag_prefix
        self.cur.execute(f"USE WAREHOUSE {WAREHOUSES[warehouse]}")
        self.cur.execute("ALTER SESSION SET USE_CACHED_RESULT = FALSE")

    def close(self):
        self.con.close()

    def _rewrite(self, sql: str) -> str:
        # compiled SQL references "lab"."<schema>"."<rel>" (lab) or COSTCI_LAB.<schema>.<rel>
        sql = re.sub(r'"lab"\."([a-z_]+)"\.', lambda m: f'COSTCI_LAB.{m.group(1).upper()}.', sql)
        for src, dst in self.map.items():
            sql = re.sub(rf"\bCOSTCI_LAB\.{src}\.", f"COSTCI_LAB.{dst}.", sql)
        return sql

    def _profiled(self, sql: str, fetch: bool = False, tag: str = "") -> Usage:
        self.cur.execute(f"ALTER SESSION SET QUERY_TAG = '{self.tag_prefix}:{tag}'")
        t0 = time.perf_counter()
        self.cur.execute(self._rewrite(sql))
        if fetch:
            self.cur.fetchall()
        wall = time.perf_counter() - t0
        qid = self.cur.sfqid
        row = self.cur.execute(
            "SELECT execution_time, total_elapsed_time, bytes_scanned, rows_produced, bytes_written "
            "FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION(RESULT_LIMIT => 100)) "
            "WHERE query_id = %s", (qid,)).fetchone()
        exec_ms, total_ms, bytes_scanned, rows, written = row or (0, 0, 0, 0, 0)
        return Usage(latency_s=(exec_ms or 0) / 1000, cpu_s=(exec_ms or 0) / 1000,
                     logical_bytes=float(bytes_scanned or 0), bytes_written=int(written or 0),
                     rows_out=int(rows or 0), wall_s=wall, statements=1)

    # ---- same surface as costci.execute.Session -------------------------------------------
    def reset_schema(self, schema: str) -> None:
        s = schema.upper()
        self.cur.execute(f"CREATE OR REPLACE TRANSIENT SCHEMA COSTCI_LAB.{s}")

    def exists(self, schema: str, name: str) -> bool:
        self.cur.execute(f"SHOW TABLES LIKE '{name.upper()}' IN SCHEMA COSTCI_LAB.{schema.upper()}")
        return bool(self.cur.fetchall())

    def build(self, name, schema, sql, materialized, unique_key=None) -> Usage:
        rel = f"COSTCI_LAB.{schema.upper()}.{name.upper()}"
        if materialized == "view":
            return self._profiled(f"CREATE OR REPLACE VIEW {rel} AS {sql}", tag=name)
        if materialized == "table":
            return self._profiled(f"CREATE OR REPLACE TRANSIENT TABLE {rel} AS {sql}", tag=name)
        if materialized == "incremental":
            if not self.exists(schema, name):     # zero-copy clone of the production target
                prod = self.map["PROD"]
                self.cur.execute(f"CREATE TRANSIENT TABLE {rel} CLONE COSTCI_LAB.{prod}.{name.upper()}")
            u = self._profiled(f"CREATE OR REPLACE TEMPORARY TABLE __INC AS {sql}", tag=name)
            u.add(self._profiled(f"DELETE FROM {rel} WHERE {unique_key} IN (SELECT {unique_key} FROM __INC)", tag=name))
            u.add(self._profiled(f"INSERT INTO {rel} SELECT * FROM __INC", tag=name))
            return u
        raise ValueError(materialized)

    def query(self, sql: str) -> Usage:
        return self._profiled(sql, fetch=True, tag="consumer")

    def explain(self, sql: str) -> list:
        """Compile-only plan: upper-bound partitions/bytes per scan; no time or credits."""
        self.cur.execute(f"EXPLAIN USING JSON {self._rewrite(sql)}")
        plan = json.loads(self.cur.fetchone()[0])
        ops = []
        for op in plan.get("Operations", [[]])[0]:
            ops.append({"op": op.get("operation"), "ec": float(op.get("bytesAssigned", 0) or 0),
                        "table": (op.get("objects") or [None])[0]})
        return ops
