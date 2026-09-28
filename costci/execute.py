"""Execute compiled workloads in a DuckDB environment and measure resource usage.

Materialisations are emulated the way dbt-duckdb would run them (the SELECT dominates cost):
  view         CREATE OR REPLACE VIEW  (build cost ~0; cost moves to consumers)
  table        CREATE OR REPLACE TABLE ... AS <select>
  incremental  delete+insert on unique_key into an existing target (cloned from prod if absent,
               which is the analog of `dbt clone` / zero-copy clone in Slim CI)
Consumers (BI queries) are plain SELECTs whose result is fetched and discarded.

Every statement is profiled with DuckDB's JSON profiler. "Logical bytes" emulates BigQuery
on-demand billing semantics: rows scanned (after zone-map pruning) x logical width of every
referenced column (INT64/FLOAT64/DATE 8, NUMERIC 16, STRING 2+len, BOOL 1).
"""
from __future__ import annotations

import json
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import duckdb

from .paths import DATA, MEMORY_LIMIT, PROD_THREADS, env_db

METRICS = ("latency_s", "cpu_s", "rows_scanned", "logical_bytes", "peak_mem_bytes",
           "spill_bytes", "bytes_written", "rows_out", "wall_s")


@dataclass
class Usage:
    latency_s: float = 0.0        # engine wall-clock (profiler)
    cpu_s: float = 0.0            # sum of operator time across threads (profiler)
    rows_scanned: int = 0
    logical_bytes: float = 0.0
    peak_mem_bytes: int = 0
    spill_bytes: int = 0
    bytes_written: int = 0
    rows_out: int = 0
    wall_s: float = 0.0           # client-side wall-clock incl. fetch
    statements: int = 0
    scans: list = field(default_factory=list)

    def add(self, o: "Usage") -> None:
        for k in ("latency_s", "cpu_s", "rows_scanned", "logical_bytes", "bytes_written",
                  "rows_out", "wall_s", "statements"):
            setattr(self, k, getattr(self, k) + getattr(o, k))
        self.peak_mem_bytes = max(self.peak_mem_bytes, o.peak_mem_bytes)
        self.spill_bytes = max(self.spill_bytes, o.spill_bytes)
        self.scans += o.scans

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("scans")
        return d


_BQ_FIXED = {"DATE": 8, "INTEGER": 8, "BIGINT": 8, "HUGEINT": 16, "DOUBLE": 8, "FLOAT": 8,
             "BOOLEAN": 1, "TIMESTAMP": 8, "SMALLINT": 8, "TINYINT": 8}


class Session:
    """One connection to one data environment."""

    def __init__(self, env: str, threads: int = PROD_THREADS):
        self.env = env
        self.con = duckdb.connect(str(env_db(env)))
        self.con.execute(f"SET threads={threads}")
        self.con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
        self.con.execute(f"SET temp_directory='{(DATA / 'spill').as_posix()}'")
        self._prof = Path(tempfile.gettempdir()) / f"costci_prof_{env}_{id(self)}.json"
        self._widths: dict[str, dict[str, float]] = {}

    def close(self) -> None:
        self.con.close()

    def set_threads(self, n: int) -> None:
        self.con.execute(f"SET threads={n}")

    # ---------------------------------------------------------------- profiling
    def _profiled(self, sql: str, fetch: bool = False) -> Usage:
        c = self.con
        self._prof.unlink(missing_ok=True)
        c.execute("PRAGMA enable_profiling='json'")
        c.execute(f"PRAGMA profiling_output='{self._prof.as_posix()}'")
        t0 = time.perf_counter()
        res = c.execute(sql)
        if fetch:
            res.fetchall()
        wall = time.perf_counter() - t0
        c.execute("PRAGMA disable_profiling")
        if not self._prof.exists():          # pure DDL (e.g. CREATE VIEW) has no physical plan
            return Usage(latency_s=wall, wall_s=wall, statements=1)
        p = json.loads(self._prof.read_text(encoding="utf-8"))
        u = Usage(latency_s=p.get("latency", 0.0), cpu_s=p.get("cpu_time", 0.0),
                  rows_scanned=p.get("cumulative_rows_scanned", 0),
                  peak_mem_bytes=p.get("system_peak_buffer_memory", 0),
                  spill_bytes=p.get("system_peak_temp_dir_size", 0),
                  bytes_written=p.get("total_bytes_written", 0),
                  rows_out=p.get("rows_returned", 0), wall_s=wall, statements=1)
        for table, cols, rows in self._scans(p):
            w = self._table_widths(table)
            referenced = [col for col in cols if col in w] or list(w)[:1]
            u.logical_bytes += rows * sum(w[col] for col in referenced)
            u.scans.append({"table": table, "rows": rows, "cols": referenced})
        return u

    @staticmethod
    def _scans(node: dict):
        out = []

        def walk(n):
            if n.get("operator_type") == "TABLE_SCAN":
                info = n.get("extra_info") or {}
                table = info.get("Table", "")
                cols = list(info.get("Projections") or [])
                filt = info.get("Filters") or ""
                filt = " ".join(filt) if isinstance(filt, list) else str(filt)
                cols += re.findall(r"[A-Za-z_][A-Za-z0-9_]*", filt)
                out.append((table, set(cols), n.get("operator_rows_scanned", 0)))
            for ch in n.get("children", []):
                walk(ch)
        walk(node)
        return out

    def _table_widths(self, table: str) -> dict[str, float]:
        if table in self._widths:
            return self._widths[table]
        parts = table.split(".")
        schema, name = parts[-2], parts[-1]
        cols = self.con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema=? AND table_name=? ORDER BY ordinal_position", [schema, name]).fetchall()
        widths, strcols = {}, []
        for col, typ in cols:
            base = typ.split("(")[0].upper()
            if base.startswith("DECIMAL"):
                widths[col] = 16.0
            elif base in _BQ_FIXED:
                widths[col] = float(_BQ_FIXED[base])
            else:
                strcols.append(col)
        if strcols:
            exprs = ", ".join(f"avg(strlen(\"{c}\"))" for c in strcols)
            vals = self.con.execute(f'SELECT {exprs} FROM "{schema}"."{name}"').fetchone()
            for c, v in zip(strcols, vals):
                widths[c] = 2.0 + float(v or 0)
        self._widths[table] = widths
        return widths

    def forget_widths(self, schema: str) -> None:
        for k in [k for k in self._widths if k.split(".")[-2] == schema]:
            del self._widths[k]

    # ---------------------------------------------------------------- materialisation
    def exists(self, schema: str, name: str) -> bool:
        return bool(self.con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema=? AND table_name=?",
            [schema, name]).fetchone()[0])

    def reset_schema(self, schema: str) -> None:
        self.con.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        self.con.execute(f"CREATE SCHEMA {schema}")
        self.forget_widths(schema)

    def _drop_if_type(self, schema: str, name: str, table_type: str) -> None:
        row = self.con.execute(
            "SELECT table_type FROM information_schema.tables WHERE table_schema=? AND table_name=?",
            [schema, name]).fetchone()
        if row and row[0] == table_type:
            kind = "VIEW" if table_type == "VIEW" else "TABLE"
            self.con.execute(f'DROP {kind} "lab"."{schema}"."{name}"')

    def build(self, name: str, schema: str, sql: str, materialized: str,
              unique_key: str | None = None) -> Usage:
        rel = f'"lab"."{schema}"."{name}"'
        if materialized == "view":
            self._drop_if_type(schema, name, "BASE TABLE")
            return self._profiled(f"CREATE OR REPLACE VIEW {rel} AS {sql}")
        if materialized == "table":
            self._drop_if_type(schema, name, "VIEW")
            return self._profiled(f"CREATE OR REPLACE TABLE {rel} AS {sql}")
        if materialized == "incremental":
            if not self.exists(schema, name):
                src = f'"lab"."prod"."{name}"'
                self.con.execute(f"CREATE TABLE {rel} AS SELECT * FROM {src}")  # clone: not measured
            u = self._profiled(f"CREATE OR REPLACE TEMP TABLE __inc AS {sql}")
            u.add(self._profiled(
                f"DELETE FROM {rel} WHERE {unique_key} IN (SELECT {unique_key} FROM __inc)"))
            u.add(self._profiled(f"INSERT INTO {rel} SELECT * FROM __inc"))
            self.con.execute("DROP TABLE __inc")
            return u
        raise ValueError(f"unsupported materialization {materialized}")

    def full_build(self, name: str, schema: str, sql: str, materialized: str) -> Usage:
        """Initial (full-refresh) build, used to create the prod schema."""
        mat = "table" if materialized == "incremental" else materialized
        return self.build(name, schema, sql, mat)

    def query(self, sql: str) -> Usage:
        return self._profiled(sql, fetch=True)

    def explain(self, sql: str) -> list:
        """Static plan (no execution): list of operators with estimated cardinality."""
        out = self.con.execute(f"EXPLAIN (FORMAT JSON) {sql}").fetchall()[0][1]
        ops = []

        def walk(n):
            info = n.get("extra_info") or {}
            ec = info.get("Estimated Cardinality")
            ops.append({"op": n.get("name"), "ec": float(ec) if ec not in (None, "") else 0.0,
                        "table": info.get("Table")})
            for ch in n.get("children", []):
                walk(ch)
        for root in json.loads(out):
            walk(root)
        return ops
