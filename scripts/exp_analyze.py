"""Analyze multi-field experiment outputs into tables + figures.

Consumes:
  scripts/exp_results.jsonl   (from exp_run.py)
  scripts/exp_tsp.json        (from exp_tsp_operators.py)
  scripts/exp_ordering.json   (from exp_ordering.py)

Produces:
  experiments/results_tables.md       markdown tables (folded into the writeup)
  experiments/results_summary.json    machine-readable aggregates
  experiments/figures/*.png           convergence / ablation / scaling / transit / operator plots

Run: venv39\\Scripts\\python.exe scripts/exp_analyze.py
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
import django

django.setup()

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

try:
    from scipy.stats import mannwhitneyu

    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXP_DIR = ROOT / "experiments"
FIG_DIR = EXP_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

N_BY_ROLE = {
    "C2close": 2,
    "C2far": 2,
    "C3line": 3,
    "C3tri": 3,
    "C3big": 3,
    "C5mixed": 5,
    "C5holes": 5,
    "C10grid": 10,
    "C5varied": 5,
    "C5size": 5,
    "C15scatter": 15,
}
ABLATIONS = ["fixed_order", "fixed_direction", "fixed_start", "fixed_drones"]
GRAN_ABLATIONS = ["single_direction", "single_start", "single_drones"]
GRAN_ROLES = ["C5size", "C5holes", "C10grid"]
ABL_ROLES = ["C3line", "C5mixed", "C5holes", "C10grid", "C5varied", "C5size", "C3big", "C15scatter"]
# Road-side control study (exp_roadside.jsonl): *R variants of three campaigns
# with the service road on the north side of every second field.
ROADSIDE_ROLES = ["C5mixedR", "C5sizeR", "C10gridR"]
ROADSIDE_ABLATIONS = ["fixed_start", "fixed_direction", "fixed_dir_start"]
NN_ROLES = ["C5mixed", "C5holes", "C10grid", "C5varied", "C5size", "C15scatter"]
ENC_ROLES = ["C10grid", "C15scatter"]
DRONE_NAMES = {
    "223": "Scout (Mini-class)",
    "224": "Light (Phantom-class)",
    "225": "Mid (Mavic-class)",
    "226": "Long (Evo-class)",
    "227": "Heavy (M300-class)",
}

# Display names for figures/paper: hyphenated, "holes" -> "obstacles".
DISPLAY = {
    "C2close": "C2-close",
    "C2far": "C2-far",
    "C3line": "C3-line",
    "C3tri": "C3-tri",
    "C3big": "C3-big",
    "C5mixed": "C5-mixed",
    "C5holes": "C5-obstacles",
    "C5varied": "C5-varied",
    "C5size": "C5-size",
    "C10grid": "C10-grid",
    "C15scatter": "C15-scatter",
    "C5mixedR": "C5-mixed-R",
    "C5sizeR": "C5-size-R",
    "C10gridR": "C10-grid-R",
}
ABL_LABELS = {
    "fixed_order": "Fixed visit order",
    "fixed_direction": "Fixed flight direction",
    "fixed_start": "Fixed start corner",
    "fixed_dir_start": "Fixed flight direction + start corner",
    "fixed_drones": "Fixed drone sequence (mid-class)",
    "single_direction": "Shared flight direction",
    "single_start": "Shared start corner",
    "single_drones": "Shared drone sequence",
}
OP_LABELS = {"rk": "random keys"}


def disp(role):
    return DISPLAY.get(role, role)


def op_label(key):
    if key in OP_LABELS:
        return OP_LABELS[key]
    cx, _, mut = key.partition("_")
    return f"{cx.upper()}+{mut}"


def load_recs():
    recs = []
    # exp_roadside.jsonl holds the road-side control study; its roles are
    # distinct (*R suffix), so the records are inert for every table that
    # filters on the canonical role lists.
    for path in sorted(HERE.glob("exp_results*.jsonl")) + sorted(HERE.glob("exp_roadside.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if "error" in r:
                    continue
                recs.append(r)
    return recs


CANON_CX, CANON_MUT = "ox", "inversion"


def is_canonical(r):
    return (
        r["method"] == "ga"
        and r["ablation"] == "full"
        and r["crossover"] == CANON_CX
        and r["mutation"] == CANON_MUT
        and r.get("truck_speed") is None
    )


def coverage_pct(rr):
    """Mean grid coverage (%) over runs, from actual unique-grid-point counts."""
    vals = []
    for r in rr:
        f = r["final"]
        if f.get("grid_total"):
            vals.append(100.0 * (f["grid_total"] - f["grid_missed"]) / f["grid_total"])
        else:  # legacy records without grid counts
            vals.append(100.0 if f.get("covered_ok") else 0.0)
    return mean(vals) if vals else float("nan")


def fmt_pm(xs):
    return f"{mean(xs):.1f} ± {pstdev(xs):.1f}" if len(xs) > 1 else f"{xs[0]:.1f}"


def pval(a, b):
    if not HAVE_SCIPY or len(a) < 3 or len(b) < 3:
        return float("nan")
    try:
        return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except ValueError:
        return float("nan")


def sig(p):
    if p != p:  # nan
        return ""
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"


# --- Transit-matrix helpers for GA order-quality ----------------------------
def order_quality_by_role():
    """For canonical GA runs, how close is the GA's chosen order to optimal?"""
    from scripts.exp_ordering import held_karp, transit_matrix
    from scripts.ga_multi_common import load_campaign

    manifest = json.loads((HERE / "exp_manifest.json").read_text(encoding="utf-8"))
    cache = {}
    for role, cid in manifest.items():
        cd = load_campaign(cid)
        M = transit_matrix(cd)
        opt, _ = held_karp(M, minimize=True)
        cache[role] = (M, opt)
    return cache


def ga_order_gap(role, order, cache):
    from scripts.exp_ordering import tour_cost

    M, opt = cache[role]
    c = tour_cost(M, order)
    return 100.0 * (c - opt) / opt if opt > 1e-9 else 0.0


def main():
    recs = load_recs()
    print(f"loaded {len(recs)} result records")
    md = ["# Multi-Field Experiment Results (auto-generated)\n"]
    summary = {}

    by = defaultdict(list)
    for r in recs:
        by[(r["role"], r["method"], r["crossover"], r["mutation"], r["ablation"], r.get("truck_speed"))].append(r)

    order_cache = order_quality_by_role()

    # ========================================================================
    # Table 1: GA vs Random Search baseline (matched budget)
    # ========================================================================
    md.append("## Table 1 — Joint GA vs Random Search (matched eval budget)\n")
    md.append("| Campaign | N | GA best_fit | RS best_fit | GA improv. | p (MWU) | GA cover | RS cover |")
    md.append("|---|---|---|---|---|---|---|---|")
    t1 = {}
    for role in sorted(N_BY_ROLE, key=lambda x: (N_BY_ROLE[x], x)):
        ga = [r for r in recs if r["role"] == role and is_canonical(r)]
        rs = [r for r in recs if r["role"] == role and r["method"] == "rs" and r.get("truck_speed") is None]
        if not ga or not rs:
            continue
        gaf = [r["best_fit"] for r in ga]
        rsf = [r["best_fit"] for r in rs]
        impr = 100.0 * (mean(rsf) - mean(gaf)) / mean(rsf)
        p = pval(gaf, rsf)
        ga_cov = coverage_pct(ga)
        rs_cov = coverage_pct(rs)
        md.append(
            f"| {role} | {N_BY_ROLE[role]} | {fmt_pm(gaf)} | {fmt_pm(rsf)} | {impr:+.1f}% | "
            f"{p:.2g} {sig(p)} | {ga_cov:.0f}% | {rs_cov:.0f}% |"
        )
        t1[role] = {"ga_mean": mean(gaf), "rs_mean": mean(rsf), "improv_pct": impr, "p": p, "n": len(gaf)}
    summary["baseline_ga_vs_rs"] = t1
    md.append("")

    # ========================================================================
    # Table 2: Ablation study (Δ vs full per dimension)
    # ========================================================================
    def _abl_table(title, note, ablations, roles, key):
        md.append(title + "\n")
        md.append(note + "\n")
        md.append("| Campaign | full | " + " | ".join(ABL_LABELS.get(a, a) for a in ablations) + " |")
        md.append("|---" * (2 + len(ablations)) + "|")
        tt = {}
        for role in roles:
            full = [r["best_fit"] for r in recs if r["role"] == role and is_canonical(r)]
            if not full:
                continue
            fm = mean(full)
            row = [f"| {role} | {fm:.1f} (base) "]
            tt[role] = {"full_mean": fm}
            for abl in ablations:
                ab = [
                    r["best_fit"]
                    for r in recs
                    if r["role"] == role
                    and r["method"] == "ga"
                    and r["ablation"] == abl
                    and r["crossover"] == CANON_CX
                    and r["mutation"] == CANON_MUT
                    and r.get("truck_speed") is None
                ]
                if not ab:
                    row.append("| — ")
                    continue
                d = 100.0 * (mean(ab) - fm) / fm
                p = pval(ab, full)
                row.append(f"| {d:+.1f}% {sig(p)} ")
                tt[role][abl] = {"mean": mean(ab), "delta_pct": d, "p": p}
            md.append("".join(row) + "|")
        summary[key] = tt
        md.append("")

    _abl_table(
        "## Table 2 — Ablation: cost increase when a dimension is not optimized",
        "Each dimension frozen at a reasonable default. Positive Δ% = freezing hurts (the dimension matters).",
        ABLATIONS,
        ABL_ROLES,
        "ablation",
    )
    _abl_table(
        "## Table 2b — Granularity: shared campaign-wide value vs per-field values",
        "Dimension still optimized but shared across fields. Positive Δ% = per-field variation matters.",
        GRAN_ABLATIONS,
        GRAN_ROLES,
        "granularity",
    )
    if any(r["role"] in ROADSIDE_ROLES for r in recs):
        _abl_table(
            "## Table 2c — Road-side control: road on the north side of every second field (*R roles)",
            "Same parcels as the base campaigns, road side alternating; base rows (uniform south roads) "
            "shown for contrast. Probes the start-corner gene when road placement varies; "
            "fixed_dir_start freezes direction AND corner together "
            "(no 180-degree-rotation compensation channel).",
            ROADSIDE_ABLATIONS,
            ["C5mixed", "C5mixedR", "C5size", "C5sizeR", "C10grid", "C10gridR"],
            "roadside",
        )

    # ========================================================================
    # Table 3: Scaling (canonical GA full)
    # ========================================================================
    md.append("## Table 3 — Scaling with number of fields (canonical GA: full, OX+inversion)\n")
    md.append(
        "| Campaign | N | best_fit | wall (s) | total time (h) | transit (h) | soft pen. % of cost | coverage | GA order-gap vs opt |"
    )
    md.append("|---|---|---|---|---|---|---|---|---|")
    t3 = {}
    for role in sorted(N_BY_ROLE, key=lambda x: (N_BY_ROLE[x], x)):
        ga = [r for r in recs if r["role"] == role and is_canonical(r)]
        if not ga:
            continue
        bf = [r["best_fit"] for r in ga]
        wall = [r["wall_s"] for r in ga]
        tr = [r["final"]["transit_time"] for r in ga]
        tt = [r["final"]["time"] for r in ga]
        pen = [100.0 * r["final"]["penalty"] / r["best_fit"] for r in ga]
        cov = coverage_pct(ga)
        gaps = [ga_order_gap(role, r["best_order"], order_cache) for r in ga if r.get("best_order")]
        gapm = mean(gaps) if gaps else float("nan")
        md.append(
            f"| {role} | {N_BY_ROLE[role]} | {fmt_pm(bf)} | {mean(wall):.1f} | {mean(tt):.2f} | {mean(tr):.2f} | "
            f"{mean(pen):.1f}% | {cov:.0f}% | {gapm:.1f}% |"
        )
        t3[role] = {
            "n": N_BY_ROLE[role],
            "best_fit": mean(bf),
            "wall_s": mean(wall),
            "total_time_h": mean(tt),
            "transit_h": mean(tr),
            "soft_penalty_pct_of_cost": mean(pen),
            "coverage_pct": cov,
            "ga_order_gap_pct": gapm,
        }
    summary["scaling"] = t3
    md.append("")

    # ========================================================================
    # Table 4: Transit-speed sensitivity
    # ========================================================================
    md.append("## Table 4 — Truck-speed sensitivity (full GA, OX+inversion)\n")
    md.append("| Campaign | truck km/h | best_fit | transit (h) | GA order-gap vs opt |")
    md.append("|---|---|---|---|---|")
    t4 = defaultdict(dict)
    for role in ["C5mixed", "C10grid"]:
        speeds = [(20.0, 20.0), (None, 40.0), (60.0, 60.0), (80.0, 80.0)]
        for ts_key, ts_disp in speeds:
            if ts_key is None:
                rr = [r for r in recs if r["role"] == role and is_canonical(r)]
            else:
                rr = [
                    r
                    for r in recs
                    if r["role"] == role
                    and r["method"] == "ga"
                    and r["ablation"] == "full"
                    and r["crossover"] == "ox"
                    and r["mutation"] == CANON_MUT
                    and r.get("truck_speed") == ts_key
                ]
            if not rr:
                continue
            bf = [r["best_fit"] for r in rr]
            tr = [r["final"]["transit_time"] for r in rr]
            gaps = [ga_order_gap(role, r["best_order"], order_cache) for r in rr if r.get("best_order")]
            gapm = mean(gaps) if gaps else float("nan")
            md.append(f"| {role} | {ts_disp:.0f} | {fmt_pm(bf)} | {mean(tr):.2f} | {gapm:.1f}% |")
            t4[role][ts_disp] = {"best_fit": mean(bf), "transit_h": mean(tr), "order_gap_pct": gapm}
    summary["transit"] = t4
    md.append("")

    # ========================================================================
    # Table 5: Operator comparison — JOINT (C10grid) vs TSP subproblem
    # ========================================================================
    md.append("## Table 5 — Ordering operators: joint cost (C10grid) vs TSP-subproblem gap\n")
    md.append(
        "Joint-cost column: n=8 seeds for ox_inversion (canonical) and rk, n=3 for the other operator "
        "pairs (robustness check only); TSP gaps are 30 repetitions each. C5* = mean over C5mixed, "
        "C5holes, C5size.\n"
    )
    md.append("| Operator | C10grid joint best_fit | C10grid TSP gap% | C15 TSP gap% | C5* TSP gap% |")
    md.append("|---|---|---|---|---|")
    tsp = json.loads((HERE / "exp_tsp.json").read_text(encoding="utf-8")) if (HERE / "exp_tsp.json").exists() else {}
    t5 = {}
    op_pairs = [(cx, mut) for cx in ["ox", "pmx", "cx"] for mut in ["swap", "insert", "inversion"]] + [("rk", "rk")]
    for cx, mut in op_pairs:
        key = f"{cx}_{mut}" if cx != "rk" else "rk"
        joint = [
            r["best_fit"]
            for r in recs
            if r["role"] == "C10grid"
            and r["method"] == "ga"
            and r["ablation"] == "full"
            and r["crossover"] == cx
            and r["mutation"] == mut
            and r.get("truck_speed") is None
        ]
        jdisp = fmt_pm(joint) if joint else "—"
        g10 = tsp.get("C10grid", {}).get("ops", {}).get(key, {}).get("mean_gap_pct", float("nan"))
        g15 = tsp.get("C15scatter", {}).get("ops", {}).get(key, {}).get("mean_gap_pct", float("nan"))
        c5 = []
        for role in ["C5mixed", "C5holes", "C5size"]:
            v = tsp.get(role, {}).get("ops", {}).get(key, {}).get("mean_gap_pct")
            if v is not None:
                c5.append(v)
        c5m = mean(c5) if c5 else float("nan")
        md.append(f"| {key} | {jdisp} | {g10:.2f}% | {g15:.2f}% | {c5m:.2f}% |")
        t5[key] = {
            "joint_c10": (mean(joint) if joint else None),
            "tsp_c10_gap": g10,
            "tsp_c15_gap": g15,
            "tsp_c5_gap": c5m,
        }
    summary["operators"] = t5
    md.append("")

    # ========================================================================
    # Table 5b: Order-gene encoding on the JOINT problem (perm vs random keys)
    # ========================================================================
    md.append("## Table 5b — Order encoding on the joint problem: permutation (OX+inversion) vs random keys\n")
    md.append("| Campaign | N | perm best_fit | rk best_fit | Δ | p (MWU) | perm order-gap | rk order-gap |")
    md.append("|---|---|---|---|---|---|---|---|")
    t5b = {}
    for role in ENC_ROLES:
        perm = [r for r in recs if r["role"] == role and is_canonical(r)]
        rk = [
            r
            for r in recs
            if r["role"] == role
            and r["method"] == "ga"
            and r["ablation"] == "full"
            and r["crossover"] == "rk"
            and r.get("truck_speed") is None
        ]
        if not perm or not rk:
            continue
        pf = [r["best_fit"] for r in perm]
        kf = [r["best_fit"] for r in rk]
        pg = [ga_order_gap(role, r["best_order"], order_cache) for r in perm if r.get("best_order")]
        kg = [ga_order_gap(role, r["best_order"], order_cache) for r in rk if r.get("best_order")]
        d = 100.0 * (mean(kf) - mean(pf)) / mean(pf)
        p = pval(kf, pf)
        md.append(
            f"| {role} | {N_BY_ROLE[role]} | {fmt_pm(pf)} | {fmt_pm(kf)} | {d:+.1f}% | {p:.2g} {sig(p)} | "
            f"{mean(pg):.1f}% | {mean(kg):.1f}% |"
        )
        t5b[role] = {"perm_mean": mean(pf), "rk_mean": mean(kf), "delta_pct": d, "p": p}
    summary["encoding"] = t5b
    md.append("")

    # ========================================================================
    # Table 6: Ordering heuristics vs exact optimum (transit hours)
    # ========================================================================
    if (HERE / "exp_ordering.json").exists():
        ordr = json.loads((HERE / "exp_ordering.json").read_text(encoding="utf-8"))
        md.append("## Table 6 — Field-ordering: heuristics vs exact optimum (transit hours)\n")
        md.append("| Campaign | N | optimal | nearest-nbr (gap) | default (gap) | worst |")
        md.append("|---|---|---|---|---|---|")
        for role in sorted(ordr, key=lambda x: (ordr[x]["n"], x)):
            o = ordr[role]
            md.append(
                f"| {role} | {o['n']} | {o['opt']:.3f} | {o['nn']:.3f} ({o['nn_gap_pct']:.0f}%) | "
                f"{o['default']:.3f} ({o['default_gap_pct']:.0f}%) | {o['worst']:.3f} |"
            )
        summary["ordering_exact"] = ordr
        md.append("")

    # ========================================================================
    # Table 7: NN-seeded hybrid vs plain joint GA
    # ========================================================================
    nn_present = any(r["method"] == "ga_nn" for r in recs)
    if nn_present:
        md.append("## Table 7 — NN-fixed hybrid vs plain joint GA (full, OX+inversion, matched budget)\n")
        md.append(
            "The hybrid freezes the order gene at the nearest-neighbour tour and spends the whole "
            "(identical) evaluation budget on the per-field coverage parameters.\n"
        )
        md.append("| Campaign | N | GA best_fit | NN-GA best_fit | Δ cost | p (MWU) | GA order-gap | NN-GA order-gap |")
        md.append("|---|---|---|---|---|---|---|---|")
        t7 = {}
        for role in NN_ROLES:
            ga = [r for r in recs if r["role"] == role and is_canonical(r)]
            nn = [r for r in recs if r["role"] == role and r["method"] == "ga_nn" and r.get("truck_speed") is None]
            if not ga or not nn:
                continue
            gaf = [r["best_fit"] for r in ga]
            nnf = [r["best_fit"] for r in nn]
            ga_gap = [ga_order_gap(role, r["best_order"], order_cache) for r in ga if r.get("best_order")]
            nn_gap = [ga_order_gap(role, r["best_order"], order_cache) for r in nn if r.get("best_order")]
            dcost = 100.0 * (mean(nnf) - mean(gaf)) / mean(gaf)
            p = pval(nnf, gaf)
            md.append(
                f"| {role} | {N_BY_ROLE[role]} | {fmt_pm(gaf)} | {fmt_pm(nnf)} | {dcost:+.1f}% | "
                f"{p:.2g} {sig(p)} | {mean(ga_gap):.1f}% | {mean(nn_gap):.1f}% |"
            )
            t7[role] = {
                "ga_mean": mean(gaf),
                "nn_mean": mean(nnf),
                "dcost_pct": dcost,
                "p": p,
                "ga_order_gap": mean(ga_gap),
                "nn_order_gap": mean(nn_gap),
            }
        summary["nn_hybrid"] = t7
        md.append("")

    # ========================================================================
    # Table 8: Fleet composition chosen by the canonical GA (from drone_usage)
    # ========================================================================
    md.append("## Table 8 — Fleet composition of the best plans (canonical GA, mean over seeds)\n")
    md.append("Share of flights performed by each airframe; |D| = distinct airframes used.\n")
    dkeys = list(DRONE_NAMES)
    md.append("| Campaign | N | |D| | " + " | ".join(DRONE_NAMES[k] for k in dkeys) + " |")
    md.append("|---|---|---|" + "---|" * len(dkeys))
    t8 = {}
    for role in sorted(N_BY_ROLE, key=lambda x: (N_BY_ROLE[x], x)):
        ga = [r for r in recs if r["role"] == role and is_canonical(r) and r["final"].get("drone_usage")]
        if not ga:
            continue
        nd = mean(len(r["final"]["drone_usage"]) for r in ga)
        shares = {k: [] for k in dkeys}
        for r in ga:
            du = r["final"]["drone_usage"]
            tot = sum(v[0] for v in du.values()) or 1
            for k in dkeys:
                shares[k].append(100.0 * du.get(k, [0, 0])[0] / tot)
        row = f"| {role} | {N_BY_ROLE[role]} | {nd:.1f} | " + " | ".join(f"{mean(shares[k]):.0f}%" for k in dkeys)
        md.append(row + " |")
        t8[role] = {"mean_distinct": nd, **{DRONE_NAMES[k]: mean(shares[k]) for k in dkeys}}
    summary["fleet_composition"] = t8
    md.append("")

    (EXP_DIR / "results_tables.md").write_text("\n".join(md), encoding="utf-8")
    (EXP_DIR / "results_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"-> {EXP_DIR / 'results_tables.md'}")
    print(f"-> {EXP_DIR / 'results_summary.json'}")

    make_figures(recs, tsp, order_cache)
    print(f"-> figures in {FIG_DIR}")


# --- Figures ---------------------------------------------------------------
def _curve_band(curves):
    L = min(len(c) for c in curves)
    arr = np.array([c[:L] for c in curves], dtype=float)
    return arr.mean(0), arr.std(0)


def make_figures(recs, tsp, order_cache=None):
    # Fig 1: GA vs RS convergence (best-so-far) for representative campaigns
    fig, axes = plt.subplots(1, 4, figsize=(19, 4.2))
    for ax, role in zip(axes, ["C3line", "C5mixed", "C10grid", "C15scatter"]):
        ga = [r["curve"] for r in recs if r["role"] == role and is_canonical(r)]
        rs = [r["curve"] for r in recs if r["role"] == role and r["method"] == "rs" and r.get("truck_speed") is None]
        if ga:
            m, s = _curve_band(ga)
            x = np.arange(1, len(m) + 1)
            ax.plot(x, m, label="Joint GA", color="C0")
            ax.fill_between(x, m - s, m + s, alpha=0.2, color="C0")
        if rs:
            m, s = _curve_band(rs)
            x = np.arange(1, len(m) + 1)
            ax.plot(x, m, label="Random search", color="C3", ls="--")
            ax.fill_between(x, m - s, m + s, alpha=0.2, color="C3")
        ax.set_title(f"{disp(role)} (N={N_BY_ROLE[role]})")
        ax.set_xlabel("generation")
        ax.set_ylabel("best-so-far cost")
        # Penalty blow-ups (day-limit violations) span orders of magnitude
        lo = min((min(c) for c in ga + rs), default=1)
        hi = max((max(c) for c in ga + rs), default=1)
        if lo > 0 and hi / lo > 50:
            ax.set_yscale("log")
        ax.legend()
    fig.suptitle("Convergence: joint GA vs matched-budget random search (mean ± SD over seeds)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig1_convergence.png", dpi=130)
    plt.close(fig)

    # Fig 2: Ablation bars (Δ% vs full)
    abl_roles = ABL_ROLES
    fig, ax = plt.subplots(figsize=(11, 5))
    width = 0.18
    xs = np.arange(len(abl_roles))
    for k, abl in enumerate(ABLATIONS):
        deltas = []
        for role in abl_roles:
            full = [r["best_fit"] for r in recs if r["role"] == role and is_canonical(r)]
            ab = [
                r["best_fit"]
                for r in recs
                if r["role"] == role
                and r["method"] == "ga"
                and r["ablation"] == abl
                and r["crossover"] == CANON_CX
                and r["mutation"] == CANON_MUT
                and r.get("truck_speed") is None
            ]
            deltas.append(100.0 * (mean(ab) - mean(full)) / mean(full) if (ab and full) else 0)
        # clip extreme bars so the small deltas stay readable; annotate true value
        y_cap = 12.0
        shown = [min(d, y_cap) for d in deltas]
        bars = ax.bar(xs + (k - 1.5) * width, shown, width, label=ABL_LABELS.get(abl, abl))
        for bar, d in zip(bars, deltas):
            if d > y_cap:
                ax.annotate(
                    f"+{d:.0f}%",
                    (bar.get_x() + bar.get_width() / 2, y_cap),
                    ha="center",
                    va="bottom",
                    fontsize=9,
                )
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylim(-8, 14)
    ax.set_xticks(xs)
    ax.set_xticklabels([disp(r) for r in abl_roles])
    ax.set_ylabel("cost change vs full GA (%)")
    ax.set_title("Ablation: cost change when one decision dimension is collapsed (bars clipped at +12%)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig2_ablation.png", dpi=130)
    plt.close(fig)

    # Fig 3: Scaling — wall time per run vs N (labeled scatter; cost is not
    # comparable across campaigns of different total area, so it is not plotted)
    roles_sorted = sorted(N_BY_ROLE, key=lambda x: N_BY_ROLE[x])
    pts = []
    for role in roles_sorted:
        ga = [r for r in recs if r["role"] == role and is_canonical(r)]
        if not ga:
            continue
        pts.append((role, N_BY_ROLE[role], mean(r["wall_s"] for r in ga)))
    if pts:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        ax.scatter([p[1] for p in pts], [p[2] for p in pts], color="C0", zorder=3)
        for role, n, w in pts:
            ax.annotate(disp(role), (n, w), textcoords="offset points", xytext=(6, 4), fontsize=9)
        ax.set_xlabel("number of fields N")
        ax.set_ylabel("wall time per GA run (s)")
        ax.set_title("Runtime scaling with number of fields")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIG_DIR / "fig3_scaling.png", dpi=130)
        plt.close(fig)

    # Fig 4: Transit-speed sensitivity. Left: C5mixed cost tracks the transit
    # share. Right: the GA's ordering quality vs the cost of transit -- when
    # transit is cheap the fitness gradient on the order gene vanishes and the
    # GA leaves ordering unoptimized (order-gap grows).
    def _sweep(role):
        speeds = [(20.0, 20), (None, 40), (60.0, 60), (80.0, 80)]
        sx, sy_fit, sy_tr, sy_gap = [], [], [], []
        for ts_key, disp in speeds:
            if ts_key is None:
                rr = [r for r in recs if r["role"] == role and is_canonical(r)]
            else:
                rr = [
                    r
                    for r in recs
                    if r["role"] == role
                    and r["method"] == "ga"
                    and r["ablation"] == "full"
                    and r["crossover"] == CANON_CX
                    and r["mutation"] == CANON_MUT
                    and r.get("truck_speed") == ts_key
                ]
            if not rr:
                continue
            sx.append(disp)
            sy_fit.append(mean(r["best_fit"] for r in rr))
            sy_tr.append(mean(r["final"]["transit_time"] for r in rr))
            gaps = [ga_order_gap(role, r["best_order"], order_cache) for r in rr if r.get("best_order")]
            sy_gap.append(mean(gaps) if gaps else float("nan"))
        return sx, sy_fit, sy_tr, sy_gap

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12, 4.2))
    sx, sy_fit, sy_tr, _ = _sweep("C5mixed")
    if sx:
        (l1,) = ax.plot(sx, sy_fit, "o-", color="C0", label="campaign cost ($, left axis)")
        ax.set_xlabel("truck speed (km/h)")
        ax.set_ylabel("campaign cost ($)", color="C0")
        axb = ax.twinx()
        (l2,) = axb.plot(sx, sy_tr, "s--", color="C3", label="transit time (h, right axis)")
        axb.set_ylabel("transit (h)", color="C3")
        ax.legend(handles=[l1, l2], fontsize=9)
        ax.set_title("C5-mixed: cost follows the transit share")
    for role, marker in [("C5mixed", "o"), ("C10grid", "s")]:
        sx, _, _, sy_gap = _sweep(role)
        if sx:
            ax2.plot(sx, sy_gap, marker + "-", label=disp(role))
    ax2.set_xlabel("truck speed (km/h)")
    ax2.set_ylabel("GA order gap vs exact optimum (%)")
    ax2.set_title("Cheap transit -> the GA stops optimizing the order")
    ax2.legend()
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig4_transit.png", dpi=130)
    plt.close(fig)

    # Fig 5: TSP operator gap bar chart (C10grid and C15scatter side by side)
    if tsp and "C10grid" in tsp:
        keys = [f"{c}_{m}" for c in ["ox", "pmx", "cx"] for m in ["swap", "insert", "inversion"]] + ["rk"]
        panels = [r for r in ["C10grid", "C15scatter"] if r in tsp]
        fig, axes = plt.subplots(1, len(panels), figsize=(7 * len(panels), 4.5), squeeze=False)
        for ax, role in zip(axes[0], panels):
            ops = tsp[role]["ops"]
            ks = [k for k in keys if k in ops]
            gaps = [ops[k]["mean_gap_pct"] for k in ks]
            errs = [ops[k]["std_gap_pct"] for k in ks]
            colors = ["C3" if k == "rk" else "C0" if "swap" in k else "C1" if "insert" in k else "C2" for k in ks]
            ax.bar([op_label(k) for k in ks], gaps, yerr=errs, color=colors, capsize=3)
            ax.set_ylabel("mean gap vs optimum (%)")
            ax.set_title(f"{disp(role)} (N={tsp[role]['n']})")
            ax.tick_params(axis="x", rotation=45)
        fig.suptitle("Ordering operators / encodings on the TSP subproblem (vs Held-Karp optimum)")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "fig5_tsp_operators.png", dpi=130)
        plt.close(fig)

    # Fig 7: fleet composition per campaign (stacked flight shares, canonical GA)
    roles_f = [
        role
        for role in sorted(N_BY_ROLE, key=lambda x: (N_BY_ROLE[x], x))
        if any(r["role"] == role and is_canonical(r) and r["final"].get("drone_usage") for r in recs)
    ]
    if roles_f:
        dkeys = list(DRONE_NAMES)
        bottoms = np.zeros(len(roles_f))
        fig, ax = plt.subplots(figsize=(10, 4.5))
        for k in dkeys:
            vals = []
            for role in roles_f:
                ga = [r for r in recs if r["role"] == role and is_canonical(r) and r["final"].get("drone_usage")]
                share = []
                for r in ga:
                    du = r["final"]["drone_usage"]
                    tot = sum(v[0] for v in du.values()) or 1
                    share.append(100.0 * du.get(k, [0, 0])[0] / tot)
                vals.append(mean(share))
            ax.bar([disp(r) for r in roles_f], vals, bottom=bottoms, label=DRONE_NAMES[k])
            bottoms += np.array(vals)
        ax.set_ylabel("share of flights (%)")
        ax.set_title("Fleet composition of the best plans (canonical GA)")
        ax.legend(fontsize=8)
        ax.tick_params(axis="x", rotation=30)
        fig.tight_layout()
        fig.savefig(FIG_DIR / "fig7_fleet.png", dpi=130)
        plt.close(fig)

    # Fig 6: two-stage planner vs joint GA — (a) campaign cost (drives the
    # recommendation), (b) order-gap mechanism. Roles sorted by N so the
    # "ties at N=5, wins at N>=10" pattern reads left to right.
    if order_cache is not None and any(r["method"] == "ga_nn" for r in recs):
        roles = [r for r in NN_ROLES if any(x["role"] == r and x["method"] == "ga_nn" for x in recs)]
        roles = sorted(roles, key=lambda x: (N_BY_ROLE.get(x, 99), x))
        cost_d, cost_sig, ga_gaps, nn_gaps = [], [], [], []
        for role in roles:
            ga_runs = [r for r in recs if r["role"] == role and is_canonical(r)]
            nn_runs = [r for r in recs if r["role"] == role and r["method"] == "ga_nn" and r.get("truck_speed") is None]
            gaf = [r["best_fit"] for r in ga_runs]
            nnf = [r["best_fit"] for r in nn_runs]
            cost_d.append(100.0 * (mean(nnf) - mean(gaf)) / mean(gaf))
            cost_sig.append(sig(pval(nnf, gaf)))
            ga_gaps.append(
                mean([ga_order_gap(role, r["best_order"], order_cache) for r in ga_runs if r.get("best_order")] or [0])
            )
            nn_gaps.append(
                mean([ga_order_gap(role, r["best_order"], order_cache) for r in nn_runs if r.get("best_order")] or [0])
            )
        xs = np.arange(len(roles))
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.5))
        bars = ax1.bar(xs, cost_d, 0.55, color=["C2" if d < 0 else "C3" for d in cost_d])
        for bar, d, s in zip(bars, cost_d, cost_sig):
            ax1.annotate(
                s,
                (bar.get_x() + bar.get_width() / 2, d + (0.15 if d >= 0 else -0.15)),
                ha="center",
                va="bottom" if d >= 0 else "top",
                fontsize=9,
            )
        ax1.axhline(0, color="k", lw=0.8)
        ax1.set_ylim(min(cost_d) - 2, max(cost_d) + 2)
        ax1.set_xticks(xs)
        ax1.set_xticklabels([disp(r) for r in roles], rotation=15)
        ax1.set_ylabel("cost change vs joint GA (%)")
        ax1.set_title(
            "(a) Campaign cost: two-stage vs joint GA\n(negative = two-stage cheaper; Mann-Whitney significance)"
        )
        ax2.bar(xs - 0.2, ga_gaps, 0.4, label="plain joint GA", color="C0")
        ax2.bar(xs + 0.2, nn_gaps, 0.4, label="two-stage planner", color="C2")
        ax2.set_xticks(xs)
        ax2.set_xticklabels([disp(r) for r in roles], rotation=15)
        ax2.set_ylabel("field-order gap vs optimum (%)")
        ax2.set_title("(b) Field-order quality (transit gap over exact optimum)")
        ax2.legend()
        fig.tight_layout()
        fig.savefig(FIG_DIR / "fig6_nn_hybrid.png", dpi=130)
        plt.close(fig)


if __name__ == "__main__":
    main()
