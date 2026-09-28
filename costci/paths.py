"""Filesystem layout and lab-wide constants."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"                      # generated, gitignored
WORK = ROOT / "work"                      # scratch per run, gitignored
RESULTS = ROOT / "results"
BENCH = ROOT / "benchmark"
BASE_PROJECT = BENCH / "project"
SCENARIOS = BENCH / "scenarios"
CONTEXT_FILE = BENCH / "production_context.yaml"

VENV_BIN = ROOT / ".venv" / "Scripts"
DBT_EXE = VENV_BIN / "dbt.exe"

# Every environment is data/<env>/lab.duckdb so the DuckDB catalog name is always "lab".
# That lets SQL compiled once by dbt run unchanged in any environment.
CATALOG = "lab"

# Local engine settings. PROD_THREADS plays the role of the production warehouse size.
PROD_THREADS = 4
MEMORY_LIMIT = "3GB"


def env_db(env: str) -> Path:
    return DATA / env / f"{CATALOG}.duckdb"
