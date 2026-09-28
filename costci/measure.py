"""Run MAIN and PR workload plans in a data environment and record resource usage.

Protocol (per environment):
  rep 0            warm-up for both variants (discarded)
  reps 1..N        interleaved, alternating order (MAIN,PR / PR,MAIN) to cancel order/cache bias
Every workload of a variant runs in dependency order within a rep, so downstream models read the
upstream tables that variant just built.

Also records static EXPLAIN plans (no execution) for every workload after the warm-up build, so
plan-based estimators see the same relations that exist at CI time.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import dbtops
from .execute import Session, Usage
from .paths import BASE_PROJECT, DATA
from .scenario import Workload, Workspace


def base_project_hash() -> str:
    h = hashlib.sha256()
    for p in sorted(BASE_PROJECT.rglob("*")):
        if p.is_file() and "target" not in p.parts and "logs" not in p.parts:
            h.update(p.relative_to(BASE_PROJECT).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def ensure_prod_schema(ws: Workspace, envs: list[str]) -> dict:
    """Build every MAIN model into schema `prod` of each environment (initial full refresh)."""
    marker_hash = base_project_hash()
    models = ws.models(ws.main_manifest)
    todo = [e for e in envs
            if not (DATA / e / "prod_schema.json").exists()
            or json.loads((DATA / e / "prod_schema.json").read_text())["hash"] != marker_hash]
    if not todo:
        return {}
    names = list(models)
    compiled = dbtops.compile_nodes(ws.main, ws.profiles, names, "prod", None, full_refresh=True)
    order = _topo_from_manifest(names, models)
    built = {}
    for env in todo:
        s = Session(env)
        s.reset_schema("prod")
        usage = {}
        for n in order:
            node = compiled[n]
            u = s.full_build(n, "prod", node["compiled_code"], node["config"]["materialized"])
            usage[n] = u.latency_s
        s.con.execute("CHECKPOINT")
        s.close()
        (DATA / env / "prod_schema.json").write_text(json.dumps({"hash": marker_hash, "build_latency_s": usage}))
        built[env] = usage
    return built


def _topo_from_manifest(names, models):
    from .scenario import _topo
    return _topo(names, models)


def _run_variant(s: Session, schema: str, plan: list[Workload]) -> dict[str, Usage]:
    out = {}
    for w in plan:
        if w.kind == "model":
            out[w.id] = s.build(w.name, schema, w.sql, w.materialized, w.unique_key)
        else:
            out[w.id] = s.query(w.sql)
    return out


def _explain(s: Session, plan: list[Workload]) -> dict[str, list]:
    out = {}
    for w in plan:
        if w.kind == "model" and w.materialized == "view":
            out[w.id] = []          # building a view executes nothing
        else:
            out[w.id] = s.explain(w.sql)
    return out


def measure_env(env: str, plans: dict[str, list[Workload]], reps: int, explain: bool = False,
                threads: int | None = None) -> dict:
    s = Session(env) if threads is None else Session(env, threads)
    schemas = {v: dbtops.SCHEMAS[v] for v in plans}
    runs: dict[str, dict[str, list]] = {v: {w.id: [] for w in plans[v]} for v in plans}
    plans_explained = {}
    for v in plans:
        s.reset_schema(schemas[v])
    for rep in range(reps + 1):
        order = ["main", "pr"] if rep % 2 == 0 else ["pr", "main"]
        for v in order:
            usage = _run_variant(s, schemas[v], plans[v])
            if rep == 0:
                continue
            for wid, u in usage.items():
                runs[v][wid].append(u.as_dict())
        if rep == 0 and explain:
            plans_explained = {v: _explain(s, plans[v]) for v in plans}
    s.close()
    return {"env": env, "reps": reps, "runs": runs, "explain": plans_explained}
