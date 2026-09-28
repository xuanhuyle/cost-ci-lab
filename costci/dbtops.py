"""Thin wrapper around real dbt (dbt-core + dbt-duckdb), invoked in-process via dbtRunner.

dbt is used for what it would do in a real Cost CI deployment: parsing, state comparison
(`state:modified`), lineage, and compilation with `--defer` (Slim CI). Execution/measurement is
done by `costci.execute`, not by `dbt run`, so that every statement can be profiled.

Compilation runs against a schema-only "compile catalog" (data/compile/lab.duckdb). Because every
environment database is named lab.duckdb, compiled SQL ("lab"."<schema>"."<model>") runs
unchanged in any data environment.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import duckdb
from dbt.cli.main import dbtRunner

from .paths import CATALOG, DATA

COMPILE_DB = DATA / "compile" / f"{CATALOG}.duckdb"
# dbt target name -> schema. ("main" is DuckDB's default schema, so CI schemas are prefixed.)
SCHEMAS = {"prod": "prod", "main": "ci_main", "pr": "ci_pr"}
MODIFIED_SUBSELECTORS = ("body", "configs", "macros", "relation", "persisted_descriptions",
                         "contract")

_runner = dbtRunner()
TIMINGS: list[tuple[str, float]] = []      # (command, seconds) for CI-latency accounting


class DbtError(RuntimeError):
    pass


def write_profiles(profiles_dir: Path) -> None:
    profiles_dir.mkdir(parents=True, exist_ok=True)
    targets = "\n".join(
        f"    {t}:\n      type: duckdb\n      path: '{COMPILE_DB.as_posix()}'\n"
        f"      schema: {s}\n      threads: 1"
        for t, s in SCHEMAS.items())
    (profiles_dir / "profiles.yml").write_text(
        f"costci_lab:\n  target: prod\n  outputs:\n{targets}\n")


def run(args: list[str], project_dir: Path, profiles_dir: Path):
    full = [*args, "--project-dir", str(project_dir), "--profiles-dir", str(profiles_dir),
            "--log-path", str(project_dir / "logs"), "--quiet"]
    t0 = time.perf_counter()
    res = _runner.invoke(full)
    TIMINGS.append((args[0], time.perf_counter() - t0))
    if not res.success:
        raise DbtError(f"dbt {' '.join(args)} failed: {res.exception}")
    return res.result


def load_manifest(project_dir: Path) -> dict:
    return json.loads((project_dir / "target" / "manifest.json").read_text(encoding="utf-8"))


def parse(project_dir: Path, profiles_dir: Path, target: str = "prod") -> dict:
    run(["parse", "--target", target], project_dir, profiles_dir)
    return load_manifest(project_dir)


def save_state(project_dir: Path, state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(project_dir / "target" / "manifest.json", state_dir / "manifest.json")


def ls(project_dir: Path, profiles_dir: Path, select: str, state_dir: Path | None = None,
       resource_type: str = "model", target: str = "prod") -> list[str]:
    args = ["ls", "--select", select, "--resource-type", resource_type, "--output", "json",
            "--output-keys", "unique_id", "--target", target]
    if state_dir is not None:
        args += ["--state", str(state_dir)]
    out = run(args, project_dir, profiles_dir) or []
    return [json.loads(x)["unique_id"] for x in out]


def _stage_placeholders(schema: str, node_names: list[str]) -> None:
    """Make exactly the selected relations exist in the target schema of the compile catalog.

    dbt-core 1.12 defers a ref when the node is unselected (with --favor-state) OR when its
    relation does not exist in the target (adapter cache lookup, dbt/context/providers.py).
    During `dbt compile` nothing is built, so without placeholders a *selected* upstream model
    would be resolved to prod — unlike `dbt build --defer`, where it is built first. The
    placeholders also make is_incremental() true, as it is for a recurring production run.
    """
    COMPILE_DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(COMPILE_DB))
    con.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    con.execute(f"CREATE SCHEMA {schema}")
    for n in node_names:
        con.execute(f"CREATE TABLE {schema}.{n} (placeholder INTEGER)")
    con.close()


def compile_nodes(project_dir: Path, profiles_dir: Path, node_names: list[str], target: str,
                  state_dir: Path | None, full_refresh: bool = False) -> dict:
    """Compile the given models into the target's schema, deferring everything else to state.

    state_dir=None compiles without deferral (used to build the prod schema itself).
    Returns {model name: manifest node} for the selected models.
    """
    if not node_names:
        return {}
    _stage_placeholders(SCHEMAS[target], node_names)
    args = ["compile", "--select", *node_names, "--target", target]
    if state_dir is not None:
        args += ["--defer", "--state", str(state_dir)]
    if full_refresh:
        args.append("--full-refresh")
    run(args, project_dir, profiles_dir)
    manifest = load_manifest(project_dir)
    return {n["name"]: n for n in manifest["nodes"].values()
            if n["resource_type"] == "model" and n["name"] in node_names}
