"""Public-PR adapter: replay natural merged PRs from a public dbt repository.

This is the minimum reusable layer the public-corpus experiment needs. It deliberately does NOT
introduce a second architecture: the economics, pool replay and metrics layers
(`costci.pools`, `costci.economics`, `costci.metrics`) are reused unchanged, and the unit of
measurement is the same one the lab used ("workload-seconds per run").

Differences from `costci.scenario`, and why:

* A scenario was "base project + overlay files". A public PR is a pair of real commits
  (`C^`, `C`) on the upstream default branch, so there is no overlay and no synthesis step.
* The lab executed compiled SQL itself (`costci.execute.Session`) so it could profile every
  statement. Here the project is a 668-node third-party dbt project with incremental models,
  post-hooks, snapshots and cross-package macro dispatch. Re-implementing its materialisation
  semantics would be a new source of error, so **real dbt executes the models** and the resource
  measurement is dbt's own per-node `execution_time` from `run_results.json`.
  That is engine latency per model: the quantity a time-metered warehouse bills, and the same
  metric E1 used as its primary truth (`METRIC = "latency_s"` in `costci/estimators.py`).

Consequence, stated once: byte-level estimators (the BigQuery dry-run analogue) cannot be computed
in this adapter. This experiment tests counterfactual *execution*, which is the mechanism the
previous stage concluded was the only reliable one.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "work" / "pub"
PROFILES = PUB / "profiles"


# --------------------------------------------------------------------------- git


def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}: {r.stderr[:400]}")
    return r.stdout


def rmtree(path: Path) -> None:
    """Windows leaves read-only bits on git object files; retry after clearing them."""
    def onerror(func, p, _exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except Exception:
            pass
    for _ in range(3):
        if not path.exists():
            return
        shutil.rmtree(path, onerror=onerror)
        if not path.exists():
            return
        time.sleep(0.5)
    if path.exists():
        raise RuntimeError(f"could not remove {path}")


def ensure_worktree(repo: Path, path: Path, sha: str) -> Path:
    """One reusable worktree per role; checkout is cheap compared with cloning."""
    if not (path / ".git").exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        git(repo, "worktree", "add", "-f", "--detach", str(path), sha)
    else:
        git(path, "checkout", "-f", "--detach", sha)
        git(path, "clean", "-xfd", "-e", "dbt_packages", "-e", "target", "-e", "logs")
    return path


# --------------------------------------------------------------------------- dbt


@dataclass
class DbtResult:
    ok: bool
    seconds: float
    stdout_tail: str = ""
    error: str = ""


class DbtProject:
    """A dbt project directory inside a worktree, with package installation cached by lockfile."""

    def __init__(self, worktree: Path, project_subdir: str, profiles_dir: Path,
                 pkg_cache: Path, duckdb_path: Path, threads: int, memory_limit: str):
        self.worktree = worktree
        self.dir = worktree / project_subdir
        self.profiles_dir = profiles_dir
        self.pkg_cache = pkg_cache
        self.duckdb_path = duckdb_path
        self.threads = threads
        self.memory_limit = memory_limit

    # -- environment -------------------------------------------------------
    def env(self) -> dict:
        e = dict(os.environ)
        e["DBT_PROFILES_DIR"] = str(self.profiles_dir)
        e["TUVA_DUCKDB_PATH"] = str(self.duckdb_path)
        e["TUVA_DUCKDB_THREADS"] = str(self.threads)
        e["TUVA_DUCKDB_MEMORY"] = self.memory_limit
        return e

    def _packages_key(self) -> str:
        """Key over the *remote* dependency pins only.

        The `local: ../` package is the worktree itself and is re-materialised per commit, so it
        must not be cached (and must not be copied into the cache: dbt falls back from symlink to
        `copytree` on Windows, which would copy `dbt_packages` into itself recursively).
        """
        h = hashlib.sha256()
        for name in ("packages.yml", "package-lock.yml", "dependencies.yml"):
            p = self.dir / name
            h.update(p.read_bytes() if p.exists() else b"")
        return h.hexdigest()[:16]

    LOCAL_PKG = "the_tuva_project"
    LOCK_SIDECAR = "__package-lock.yml"

    def _copy_local_package(self) -> None:
        """Materialise the `local: ../` package without recursing into dbt_packages."""
        dest = self.dir / "dbt_packages" / self.LOCAL_PKG
        rmtree(dest)
        ignore = shutil.ignore_patterns("dbt_packages", "target", "logs", ".git", ".github")
        shutil.copytree(self.worktree, dest, ignore=ignore)

    # -- commands ----------------------------------------------------------
    def run(self, args: list[str], timeout: int = 5400) -> DbtResult:
        cmd = [str(ROOT / ".venv" / "Scripts" / "dbt.exe"), *args,
               "--project-dir", str(self.dir), "--profiles-dir", str(self.profiles_dir)]
        t0 = time.perf_counter()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env=self.env(), timeout=timeout)
        except subprocess.TimeoutExpired:
            return DbtResult(False, time.perf_counter() - t0, error="TIMEOUT")
        out = (r.stdout or "") + (r.stderr or "")
        return DbtResult(r.returncode == 0, time.perf_counter() - t0,
                         stdout_tail=out[-4000:], error="" if r.returncode == 0 else out[-4000:])

    def deps(self) -> DbtResult:
        """Install packages. Remote packages are cached by their pinned set; the local package
        (the worktree itself) is always re-materialised for the current commit."""
        key = self._packages_key()
        cached = self.pkg_cache / key
        target = self.dir / "dbt_packages"
        t0 = time.perf_counter()
        rmtree(target)
        if cached.exists():
            shutil.copytree(cached, target, ignore=shutil.ignore_patterns(self.LOCK_SIDECAR))
            self._copy_local_package()
            # dbt resolves the expected package set from package-lock.yml; without it, a project
            # whose packages.yml lists one `local:` entry but installs transitive dependencies
            # fails the installed-count check in dbt/config/runtime.py.
            sidecar = cached / self.LOCK_SIDECAR
            if sidecar.exists():
                shutil.copy(sidecar, self.dir / "package-lock.yml")
            return DbtResult(True, time.perf_counter() - t0, stdout_tail="(cached remote packages)")
        res = self.run(["deps"])
        if res.ok and target.exists():
            self.pkg_cache.mkdir(parents=True, exist_ok=True)
            tmp = self.pkg_cache / (key + ".tmp")
            rmtree(tmp)
            shutil.copytree(target, tmp, ignore=shutil.ignore_patterns(self.LOCAL_PKG))
            lock = self.dir / "package-lock.yml"
            if lock.exists():
                shutil.copy(lock, tmp / self.LOCK_SIDECAR)
            if cached.exists():
                rmtree(cached)
            tmp.rename(cached)
        return res

    def parse(self, dbt_vars: dict | None = None) -> DbtResult:
        args = ["parse"]
        if dbt_vars:
            args += ["--vars", json.dumps(dbt_vars)]
        return self.run(args)

    def manifest(self) -> dict:
        return json.loads((self.dir / "target" / "manifest.json").read_text(encoding="utf-8"))

    def run_results(self) -> dict:
        p = self.dir / "target" / "run_results.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"results": []}

    def save_state(self, state_dir: Path) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.dir / "target" / "manifest.json", state_dir / "manifest.json")

    def ls(self, select: str, state_dir: Path | None = None, resource_type: str = "model",
           dbt_vars: dict | None = None) -> tuple[list[str], DbtResult]:
        args = ["ls", "--select", select, "--resource-type", resource_type,
                "--output", "json", "--output-keys", "unique_id"]
        if state_dir is not None:
            args += ["--state", str(state_dir)]
        if dbt_vars:
            args += ["--vars", json.dumps(dbt_vars)]
        res = self.run(args)
        ids = []
        for line in res.stdout_tail.splitlines():
            line = line.strip()
            if line.startswith("{") and "unique_id" in line:
                try:
                    ids.append(json.loads(line)["unique_id"])
                except Exception:
                    pass
        return ids, res


# --------------------------------------------------------------------------- measurement


@dataclass
class NodeTiming:
    unique_id: str
    status: str
    execution_time: float
    rows_affected: int | None = None


@dataclass
class RunMeasurement:
    """One execution of a node set, in one regime, under one code variant."""
    variant: str                  # "main" | "pr"
    regime: str                   # "ci" | "production"
    rep: int
    ok: bool
    wall_s: float
    nodes: dict[str, float] = field(default_factory=dict)   # unique_id -> execution_time
    failed: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def total_s(self) -> float:
        return sum(self.nodes.values())

    def as_dict(self) -> dict:
        d = asdict(self)
        d["total_s"] = self.total_s
        return d


def harvest(project: DbtProject) -> tuple[dict[str, float], list[str]]:
    """Per-node execution_time from run_results.json; model nodes only."""
    rr = project.run_results()
    times, failed = {}, []
    for r in rr.get("results", []):
        uid = r.get("unique_id", "")
        if not uid.startswith("model."):
            continue
        status = r.get("status")
        if status in ("error", "fail"):
            failed.append(uid)
            continue
        if status == "skipped":
            continue
        times[uid] = float(r.get("execution_time") or 0.0)
    return times, failed


def write_profile(path: Path, duckdb_path: Path, threads: int, memory_limit: str,
                  extra_settings: dict | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    settings = {"memory_limit": memory_limit, "s3_region": "us-east-1",
                **(extra_settings or {})}
    lines = "\n".join(f"        {k}: '{v}'" for k, v in settings.items())
    (path / "profiles.yml").write_text(
        "default:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{duckdb_path.as_posix()}'\n"
        f"      threads: {threads}\n"
        "      extensions:\n"
        "        - httpfs\n"
        "      settings:\n"
        f"{lines}\n", encoding="utf-8")
