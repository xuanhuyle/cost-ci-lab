"""Render every results/*.json into markdown tables under results/tables/ (no hand transcription).

Usage: python -m experiments.report
"""
from __future__ import annotations

import json
import math
import statistics as st

from costci.paths import RESULTS

T = RESULTS / "tables"


def load(name):
    p = RESULTS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def pct(x, digits=0):
    if x is None:
        return "n/a"
    if isinstance(x, float) and math.isinf(x):
        return "new" if x > 0 else "-inf"
    return f"{x * 100:+.{digits}f}%"


def num(x, d=2):
    return "n/a" if x is None else f"{x:.{d}f}"


def write(name, lines):
    T.mkdir(parents=True, exist_ok=True)
    (T / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def attribution():
    a = load("attribution.json")
    if not a:
        return
    lines = ["| scenario | files changed | dbt state:modified | rendered-SQL diff | missed by dbt | flagged, render-identical | modified+ | consumers |",
             "|---|---|---|---|---|---|---|---|"]
    for sid, r in a.items():
        lines.append(f"| {sid} | {', '.join(r['changed_files'])} | {', '.join(r['dbt_modified']) or '-'} | "
                     f"{', '.join(r['rendered_modified']) or '-'} | {', '.join(r['missed_by_dbt']) or '-'} | "
                     f"{', '.join(r['flagged_but_render_identical']) or '-'} | {len(r['modified_plus'])} | "
                     f"{', '.join(r['consumers']) or '-'} |")
    write("attribution.md", lines)


def economics():
    e = load("economics.json")
    if not e:
        return
    pools = ["own_context", "snowflake_dedicated", "snowflake_always_on_bi", "attributed_per_second",
             "bigquery_on_demand", "bigquery_editions", "databricks_sql_serverless"]
    lines = ["Monthly $ (SIMULATED; ASSUMED unit scaling κ=100). Cell = truth marginal / naive attributed.", "",
             "| scenario | " + " | ".join(pools) + " |", "|---|" + "---|" * len(pools)]
    for r in e:
        lines.append(f"| {r['id']} | " + " | ".join(
            f"{r['pools'][p]['truth_marginal']:+.0f} / {r['pools'][p]['naive_attributed']:+.0f}" for p in pools) + " |")
    # summary per pool: how often naive attribution misclassifies materiality of the marginal $
    lines += ["", "| pool config | scenarios where marginal ≈ 0 (<$5) but naive ≥ $50 | median naive/marginal (both ≥ $5) | sign disagreements |",
              "|---|---|---|---|"]
    for p in pools:
        absorbed, ratios, sign = 0, [], 0
        for r in e:
            t, n = r["pools"][p]["truth_marginal"], r["pools"][p]["naive_attributed"]
            if abs(t) < 5 and abs(n) >= 50:
                absorbed += 1
            if abs(t) >= 5 and abs(n) >= 5:
                ratios.append(n / t)
                if n * t < 0:
                    sign += 1
        lines.append(f"| {p} | {absorbed} | {num(st.median(ratios)) if ratios else 'n/a'} | {sign} |")
    lines += ["", "Sensitivity to κ (snowflake_dedicated): truth marginal / naive attributed per scenario", "",
              "| scenario | κ=10 | κ=100 | κ=1000 |", "|---|---|---|---|"]
    for r in e:
        cells = [f"{r['kappa'][k]['truth_marginal']:+.0f} / {r['kappa'][k]['naive_attributed']:+.0f}"
                 for k in ("10", "100", "1000")]
        lines.append(f"| {r['id']} | " + " | ".join(cells) + " |")
    write("economics_summary.md", lines)


def transfer():
    t = load("transfer.json")
    if not t:
        return
    lines = ["| scenario | prod 4 threads (ref) | CI 1 thread | prod under load | cold single run |",
             "|---|---|---|---|---|"]
    for sid, r in t.items():
        ref = r["prod_4t"].get("ratio")
        cells = [num(ref, 3)]
        for k in ("ci_1t", "prod_4t_loaded", "cold_single"):
            x = r[k].get("ratio")
            cells.append(f"{num(x, 3)} ({pct(x / ref - 1) if (x and ref) else 'n/a'})")
        lines.append(f"| {sid} | " + " | ".join(cells) + " |")
    lines.append("\nCell = PR/MAIN total-latency ratio (difference vs the production reference).")
    lines += ["", "| scenario | slowdown of MAIN under load | slowdown of PR under load |", "|---|---|---|"]
    for sid, r in t.items():
        a, b = r["prod_4t"], r["prod_4t_loaded"]
        if "error" in a or "error" in b:
            lines.append(f"| {sid} | error | {(b.get('error') or a.get('error'))[:60]} |")
            continue
        lines.append(f"| {sid} | {num(b['main_s'] / a['main_s'])}x | {num(b['pr_s'] / a['pr_s'])}x |")
    write("transfer.md", lines)


def layout():
    l = load("layout.json")
    if not l:
        return
    lines = ["| scenario | ratio, default row groups (~26 days) | ratio, 8,192-row groups (~1.7 days) |",
             "|---|---|---|"]
    for sid, r in l.items():
        lines.append(f"| {sid} | {num(r['coarse_default_rowgroups']['ratio'], 3)} | {num(r['fine_8192_rowgroups']['ratio'], 3)} |")
    write("layout.md", lines)


def downstream():
    d = load("downstream.json")
    if not d:
        return
    strat = ["direct", "plus_1hop", "all_models", "all_with_consumers", "elasticity_prod", "elasticity_key10"]
    lines = ["| scenario | truth | " + " | ".join(strat) + " |", "|---|---|" + "---|" * len(strat)]
    for sid, r in d.items():
        lines.append(f"| {sid} | {pct(r['truth_rel'])} | " + " | ".join(pct(r['strategies'][s]['rel']) for s in strat) + " |")
    lines += ["", "CI execution (lab-seconds, MAIN+PR once) by strategy:", "",
              "| scenario | " + " | ".join(strat[:4]) + " | elasticity |", "|---|" + "---|" * 5]
    for sid, r in d.items():
        lines.append(f"| {sid} | " + " | ".join(num(r['strategies'][s]['ci_exec_lab_s'], 1) for s in strat[:4])
                     + f" | {num(r['strategies']['elasticity_prod']['ci_exec_lab_s'], 1)} |")
    write("downstream.md", lines)


def uncertainty():
    u = load("uncertainty.json")
    if not u:
        return
    lines = ["| estimator | 80% interval coverage | n | direction accuracy by confidence label |", "|---|---|---|---|"]
    for est, s in u["summary"].items():
        labels = ", ".join(f"{k}: {num(v[0])} (n={v[1]})" for k, v in s["direction_acc_by_label"].items())
        lines.append(f"| {est} | {num(s['coverage_80'])} | {s['n']} | {labels} |")
    lines += ["", "| scenario | estimator | point | 80% interval | truth | inside | label |", "|---|---|---|---|---|---|---|"]
    for r in u["rows"]:
        lines.append(f"| {r['scenario']} | {r['estimator']} | {pct(r['point'])} | [{pct(r['lo'])}, {pct(r['hi'])}] | "
                     f"{pct(r['truth'])} | {r['inside']} | {r['label']} |")
    write("uncertainty.md", lines)


def calibration():
    c = load("calibration.json")
    if not c:
        return
    lines = ["| estimator | pairs | median abs log error before | after global factor (LOO) | after per-class factor (LOO) | learned factor |",
             "|---|---|---|---|---|---|"]
    for est, r in c.items():
        lines.append(f"| {est} | {r['n_pairs']} | {num(r['median_abs_log_err_before'])} | {num(r['median_abs_log_err_global'])} | "
                     f"{num(r['median_abs_log_err_by_class'])} | {num(r['learned_global_factor'])} |")
    write("calibration.md", lines)


def frequency():
    f = load("frequency.json")
    if not f:
        return
    lines = ["| pattern (SIMULATED) | median rel. error, trailing 30 d | p90 | median rel. error, trailing 90 d | Poisson 80% coverage | empirical-range coverage |",
             "|---|---|---|---|---|---|"]
    for p, r in f.items():
        lines.append(f"| {p} | {num(r['median_rel_err_trailing30'], 3)} | {num(r['p90_rel_err_trailing30'], 3)} | "
                     f"{num(r['median_rel_err_trailing90'], 3)} | {num(r['coverage_poisson80'])} | {num(r['coverage_empirical_range'])} |")
    write("frequency.md", lines)


def ci_econ():
    c = load("ci_economics.json")
    if not c:
        return
    lines = ["| strategy | k = production-run equivalents per CI analysis (MEASURED, median) | break-even runs/month: min / median / max over assumption grid |",
             "|---|---|---|"]
    for s, kv in c["k_measured"].items():
        fs = sorted(r["breakeven_runs_per_month"] for r in c["breakeven_runs_per_month"][s])
        lines.append(f"| {s} | {num(kv)} | {fs[0]:.1f} / {fs[len(fs) // 2]:.1f} / {fs[-1]:.1f} |")
    write("ci_economics.md", lines)


def main():
    for f in (attribution, economics, transfer, layout, downstream, uncertainty, calibration, frequency, ci_econ):
        f()
    print("tables:", sorted(p.name for p in T.glob("*.md")))


if __name__ == "__main__":
    main()
