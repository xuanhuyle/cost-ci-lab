"""Scenario = one pull request against the base dbt project.

Responsibilities (the "change detection" and "workload mapping" layers of the architecture):
  1. materialise MAIN and PR project copies (PR = base + overlay files - deleted files)
  2. record the code diff (git diff --no-index)
  3. ask dbt which models changed (state:modified and sub-selectors) and what is downstream
     (state:modified+)
  4. map changed relations to production workloads: dbt jobs (schedule) and non-dbt consumers
     (BI queries) that read them — the lab's stand-in for ACCESS_HISTORY / JOBS.referenced_tables
  5. compile MAIN and PR versions of the affected models with --defer (Slim CI semantics)

Scenario files never contain expected estimator outputs; ground truth is measured.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import dbtops
from .paths import BASE_PROJECT, CONTEXT_FILE, SCENARIOS, WORK

REF_RE = re.compile(r"\{\{\s*ref\('([A-Za-z0-9_]+)'\)\s*\}\}")


@dataclass
class Scenario:
    id: str
    title: str
    category: str                      # human label only; never used for scoring
    description: str
    overlay: dict[str, str] = field(default_factory=dict)
    delete: list[str] = field(default_factory=list)
    context_overrides: dict = field(default_factory=dict)
    dir: Path | None = None


def load_scenarios(only: list[str] | None = None) -> list[Scenario]:
    out = []
    for d in sorted(p for p in SCENARIOS.iterdir() if p.is_dir()):
        spec = yaml.safe_load((d / "scenario.yaml").read_text(encoding="utf-8"))
        if only and spec["id"] not in only:
            continue
        out.append(Scenario(id=spec["id"], title=spec["title"], category=spec["category"],
                            description=spec.get("description", ""),
                            overlay=spec.get("overlay") or {}, delete=spec.get("delete") or [],
                            context_overrides=spec.get("context_overrides") or {}, dir=d))
    return out


def load_context(overrides: dict | None = None) -> dict:
    ctx = yaml.safe_load(CONTEXT_FILE.read_text(encoding="utf-8"))
    for path, value in (overrides or {}).items():      # dotted-path overrides, e.g. pools.bi_wh.kind
        node = ctx
        keys = path.split(".")
        for k in keys[:-1]:
            node = node[int(k)] if isinstance(node, list) else node[k]
        node[keys[-1]] = value
    return ctx


@dataclass
class Workload:
    id: str                       # "model:<name>" or "consumer:<id>"
    kind: str                     # model | consumer
    name: str
    sql: str
    materialized: str | None
    unique_key: str | None
    job: str | None
    runs_per_month: float
    pool: str


@dataclass
class ChangeSet:
    changed_files: list[str]
    modified: list[str]
    modified_by: dict[str, list[str]]
    modified_plus: list[str]
    new_models: list[str]
    removed_models: list[str]
    consumers: list[str]


@dataclass
class Prepared:
    scenario: Scenario
    context: dict
    changes: ChangeSet
    plans: dict[str, list[Workload]]           # variant -> ordered workloads
    dbt_seconds: float


class Workspace:
    """Shared MAIN project + prod state, reused across scenarios."""

    def __init__(self, root: Path = WORK / "bench"):
        self.root = root
        self.profiles = root / "profiles"
        self.main = root / "main"
        self.state = root / "state_prod"
        dbtops.write_profiles(self.profiles)
        if self.main.exists():
            shutil.rmtree(self.main)
        shutil.copytree(BASE_PROJECT, self.main, ignore=shutil.ignore_patterns("target", "logs"))
        self.main_manifest = dbtops.parse(self.main, self.profiles, "prod")
        dbtops.save_state(self.main, self.state)

    def models(self, manifest: dict) -> dict[str, dict]:
        return {n["name"]: n for n in manifest["nodes"].values() if n["resource_type"] == "model"}


def _names(unique_ids: list[str]) -> list[str]:
    return [u.split(".")[-1] for u in unique_ids]


def _topo(names: list[str], models: dict[str, dict]) -> list[str]:
    ids = {models[n]["unique_id"]: n for n in names}
    order, seen = [], set()

    def visit(n):
        if n in seen:
            return
        seen.add(n)
        for dep in models[n]["depends_on"]["nodes"]:
            if dep in ids:
                visit(ids[dep])
        order.append(n)
    for n in sorted(names):
        visit(n)
    return order


def job_for(model: dict, ctx: dict) -> dict:
    for job in ctx["jobs"]:
        if model["name"] in (job.get("models") or []):
            return job
        if set(job.get("tags") or []) & set(model.get("tags") or []):
            return job
    return next(j for j in ctx["jobs"] if j.get("default"))


def consumer_refs(sql: str) -> list[str]:
    return REF_RE.findall(sql)


def resolve_consumer(sql: str, rebuilt: set[str], schema: str) -> str:
    return REF_RE.sub(lambda m: f'"lab"."{schema if m.group(1) in rebuilt else "prod"}"."{m.group(1)}"',
                      sql)


def prepare(ws: Workspace, sc: Scenario) -> Prepared:
    t0 = sum(t for _, t in dbtops.TIMINGS)
    ctx = load_context(sc.context_overrides)
    pr = ws.root / "scenarios" / sc.id / "pr"
    if pr.exists():
        shutil.rmtree(pr)
    shutil.copytree(BASE_PROJECT, pr, ignore=shutil.ignore_patterns("target", "logs"))
    for dest, src in sc.overlay.items():
        target = pr / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(sc.dir / src, target)
    for dest in sc.delete:
        (pr / dest).unlink()

    diff = subprocess.run(["git", "diff", "--no-index", "--name-only", str(BASE_PROJECT), str(pr)],
                          capture_output=True, text=True)
    changed = sorted({Path(line).relative_to(pr).as_posix() for line in diff.stdout.splitlines()
                      if line.strip() and Path(line).is_relative_to(pr)}
                     | {d for d in sc.delete})

    pr_manifest = dbtops.parse(pr, ws.profiles, "prod")
    modified = _names(dbtops.ls(pr, ws.profiles, "state:modified", ws.state))
    modified_by = {s: _names(dbtops.ls(pr, ws.profiles, f"state:modified.{s}", ws.state))
                   for s in dbtops.MODIFIED_SUBSELECTORS}
    modified_plus = _names(dbtops.ls(pr, ws.profiles, "state:modified+", ws.state))

    main_models = ws.models(ws.main_manifest)
    pr_models = ws.models(pr_manifest)
    new = sorted(set(pr_models) - set(main_models))
    removed = sorted(set(main_models) - set(pr_models))

    pr_nodes = _topo(modified_plus, pr_models)
    main_nodes = _topo([n for n in modified_plus if n in main_models], main_models)
    rebuilt = set(modified_plus)
    consumers = [c for c in ctx["consumers"] if set(consumer_refs(c["sql"])) & rebuilt]

    compiled = {
        "pr": dbtops.compile_nodes(pr, ws.profiles, pr_nodes, "pr", ws.state),
        "main": dbtops.compile_nodes(ws.main, ws.profiles, main_nodes, "main", ws.state),
    }
    plans = {}
    for variant, nodes, models in (("main", main_nodes, main_models), ("pr", pr_nodes, pr_models)):
        schema = dbtops.SCHEMAS[variant]
        wl = []
        for n in nodes:
            node = compiled[variant][n]
            job = job_for(models[n], ctx)
            wl.append(Workload(id=f"model:{n}", kind="model", name=n, sql=node["compiled_code"],
                               materialized=node["config"]["materialized"],
                               unique_key=node["config"].get("unique_key"), job=job["id"],
                               runs_per_month=job["runs_per_month"], pool=job["pool"]))
        for c in consumers:
            wl.append(Workload(id=f"consumer:{c['id']}", kind="consumer", name=c["id"],
                               sql=resolve_consumer(c["sql"], set(nodes), schema),
                               materialized=None, unique_key=None, job=None,
                               runs_per_month=c["runs_per_month"], pool=c["pool"]))
        plans[variant] = wl
    changes = ChangeSet(changed_files=changed, modified=modified, modified_by=modified_by,
                        modified_plus=modified_plus, new_models=new, removed_models=removed,
                        consumers=[c["id"] for c in consumers])
    return Prepared(scenario=sc, context=ctx, changes=changes, plans=plans,
                    dbt_seconds=sum(t for _, t in dbtops.TIMINGS) - t0)
