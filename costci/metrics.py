"""Decision-usefulness metrics for cost-impact estimates.

A scenario's impact is expressed relative to the monthly cost of the workloads it affects:
    rel = (monthly cost with PR - monthly cost with MAIN) / monthly cost with MAIN
New workloads have no MAIN cost; rel = +inf and they count as large regressions.
"""
from __future__ import annotations

import math

MATERIAL = 0.10          # |rel| below this is "immaterial" (chosen above the lab's noise floor)
LARGE = 0.50             # "large regression"
BUCKETS = [(-math.inf, -1.0), (-1.0, -0.5), (-0.5, -0.25), (-0.25, -0.10), (-0.10, 0.10),
           (0.10, 0.25), (0.25, 0.50), (0.50, 1.00), (1.00, math.inf)]
BUCKET_LABELS = ["<-100%", "-100..-50%", "-50..-25%", "-25..-10%", "±10%", "+10..25%",
                 "+25..50%", "+50..100%", ">+100%"]


def direction(rel: float | None) -> str | None:
    if rel is None:
        return None
    if rel >= MATERIAL:
        return "increase"
    if rel <= -MATERIAL:
        return "decrease"
    return "immaterial"


def bucket(rel: float | None) -> int | None:
    if rel is None:
        return None
    for i, (lo, hi) in enumerate(BUCKETS):
        if lo <= rel < hi:
            return i
    return len(BUCKETS) - 1


def spearman(xs: list[float], ys: list[float]) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None
             and math.isfinite(x) and math.isfinite(y)]
    n = len(pairs)
    if n < 3:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else None


def score(rows: list[dict], key: str) -> dict:
    """rows: [{truth_rel, <key>_rel, truth_delta, <key>_delta}] -> metrics for one estimator."""
    n = len(rows)
    est = [r.get(f"{key}_rel") for r in rows]
    tru = [r["truth_rel"] for r in rows]
    have = [e is not None for e in est]
    tdir = [direction(t) for t in tru]
    edir = [direction(e) for e in est]
    material = [i for i in range(n) if tdir[i] != "immaterial"]
    immaterial = [i for i in range(n) if tdir[i] == "immaterial"]
    large = [i for i in range(n) if tru[i] is not None and tru[i] >= LARGE]
    out = {
        "n": n,
        "coverage": sum(have) / n if n else None,
        "direction_acc_all": _frac([edir[i] == tdir[i] for i in range(n)]),
        "direction_acc_material": _frac([edir[i] == tdir[i] for i in material]),
        "large_regression_recall": _frac([edir[i] == "increase" for i in large]),
        "large_regression_recall_strict": _frac([est[i] is not None and est[i] >= LARGE for i in large]),
        "false_warning_rate": _frac([edir[i] in ("increase", "decrease") for i in immaterial]),
        "bucket_exact": _frac([bucket(est[i]) == bucket(tru[i]) for i in range(n)]),
        "bucket_within_one": _frac([est[i] is not None and abs(bucket(est[i]) - bucket(tru[i])) <= 1
                                    for i in range(n)]),
        "spearman_monthly_delta": spearman([r.get(f"{key}_delta") for r in rows],
                                           [r["truth_delta"] for r in rows]),
        "n_material": len(material), "n_immaterial": len(immaterial), "n_large": len(large),
    }
    errs = []
    for i in material:
        e, t = rows[i].get(f"{key}_delta"), rows[i]["truth_delta"]
        if e is not None and t and e * t > 0:
            errs.append(abs(math.log(e / t)))
    out["median_abs_log_error_material"] = sorted(errs)[len(errs) // 2] if errs else None
    out["within_2x_material"] = _frac([x <= math.log(2) for x in errs]) if errs else None
    return out


def _frac(bools: list[bool]) -> float | None:
    return sum(bools) / len(bools) if bools else None
