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
    "C5mixed": 5,
    "C5holes": 5,
    "C10grid": 10,
    "C5varied": 5,
}
ABLATIONS = ["fixed_order", "single_direction", "single_start", "single_drones"]
ABL_ROLES = ["C3line", "C5mixed", "C5holes", "C10grid", "C5varied"]
NN_ROLES = ["C5mixed", "C5holes", "C10grid", "C5varied"]


def load_recs():
    recs = []
    for path in sorted(HERE.glob("exp_results*.jsonl")):
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


def is_canonical(r):
    return (
        r["method"] == "ga"
        and r["ablation"] == "full"
        and r["crossover"] == "ox"
        and r["mutation"] == "swap"
        and r.get("truck_speed") is None
    )


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
        ga_cov = 100.0 * sum(r["final"]["covered_ok"] for r in ga) / len(ga)
        rs_cov = 100.0 * sum(r["final"]["covered_ok"] for r in rs) / len(rs)
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
    md.append("## Table 2 — Ablation: cost increase when a dimension is disabled\n")
    md.append("Positive Δ% = disabling that dimension makes the solution *worse* (so that dimension matters).\n")
    md.append("| Campaign | full | fixed_order | single_direction | single_start | single_drones |")
    md.append("|---|---|---|---|---|---|")
    t2 = {}
    for role in ABL_ROLES:
        full = [r["best_fit"] for r in recs if r["role"] == role and is_canonical(r)]
        if not full:
            continue
        fm = mean(full)
        row = [f"| {role} | {fm:.1f} (base) "]
        t2[role] = {"full_mean": fm}
        for abl in ABLATIONS:
            ab = [
                r["best_fit"]
                for r in recs
                if r["role"] == role
                and r["method"] == "ga"
                and r["ablation"] == abl
                and r["crossover"] == "ox"
                and r["mutation"] == "swap"
                and r.get("truck_speed") is None
            ]
            if not ab:
                row.append("| — ")
                continue
            d = 100.0 * (mean(ab) - fm) / fm
            p = pval(ab, full)
            row.append(f"| {d:+.1f}% {sig(p)} ")
            t2[role][abl] = {"mean": mean(ab), "delta_pct": d, "p": p}
        md.append("".join(row) + "|")
    summary["ablation"] = t2
    md.append("")

    # ========================================================================
    # Table 3: Scaling (canonical GA full)
    # ========================================================================
    md.append("## Table 3 — Scaling with number of fields (canonical GA: full, OX+swap)\n")
    md.append("| Campaign | N | best_fit | wall (s) | transit (h) | coverage | GA order-gap vs opt |")
    md.append("|---|---|---|---|---|---|---|")
    t3 = {}
    for role in sorted(N_BY_ROLE, key=lambda x: (N_BY_ROLE[x], x)):
        ga = [r for r in recs if r["role"] == role and is_canonical(r)]
        if not ga:
            continue
        bf = [r["best_fit"] for r in ga]
        wall = [r["wall_s"] for r in ga]
        tr = [r["final"]["transit_time"] for r in ga]
        cov = 100.0 * sum(r["final"]["covered_ok"] for r in ga) / len(ga)
        gaps = [ga_order_gap(role, r["best_order"], order_cache) for r in ga if r.get("best_order")]
        gapm = mean(gaps) if gaps else float("nan")
        md.append(
            f"| {role} | {N_BY_ROLE[role]} | {fmt_pm(bf)} | {mean(wall):.1f} | {mean(tr):.2f} | "
            f"{cov:.0f}% | {gapm:.1f}% |"
        )
        t3[role] = {
            "n": N_BY_ROLE[role],
            "best_fit": mean(bf),
            "wall_s": mean(wall),
            "transit_h": mean(tr),
            "coverage_pct": cov,
            "ga_order_gap_pct": gapm,
        }
    summary["scaling"] = t3
    md.append("")

    # ========================================================================
    # Table 4: Transit-speed sensitivity
    # ========================================================================
    md.append("## Table 4 — Truck-speed sensitivity (full GA, OX+swap)\n")
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
                    and r["mutation"] == "swap"
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
    md.append("Joint best_fit barely moves (ordering is a minor cost lever); the TSP gap is the honest signal.\n")
    md.append("| Operator | C10grid joint best_fit | C10grid TSP gap% | C5* TSP gap% |")
    md.append("|---|---|---|---|")
    tsp = json.loads((HERE / "exp_tsp.json").read_text(encoding="utf-8")) if (HERE / "exp_tsp.json").exists() else {}
    t5 = {}
    for cx in ["ox", "pmx", "cx"]:
        for mut in ["swap", "insert", "inversion"]:
            key = f"{cx}_{mut}"
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
            c5 = []
            for role in ["C5mixed", "C5holes"]:
                v = tsp.get(role, {}).get("ops", {}).get(key, {}).get("mean_gap_pct")
                if v is not None:
                    c5.append(v)
            c5m = mean(c5) if c5 else float("nan")
            md.append(f"| {key} | {jdisp} | {g10:.2f}% | {c5m:.2f}% |")
            t5[key] = {"joint_c10": (mean(joint) if joint else None), "tsp_c10_gap": g10, "tsp_c5_gap": c5m}
    summary["operators"] = t5
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
        md.append("## Table 7 — NN-seeded hybrid vs plain joint GA (full, OX+swap)\n")
        md.append(
            "Seeding the initial order with nearest-neighbour fixes the GA's neglected ordering at no extra budget.\n"
        )
        md.append("| Campaign | N | GA best_fit | NN-GA best_fit | Δ cost | GA order-gap | NN-GA order-gap |")
        md.append("|---|---|---|---|---|---|---|")
        t7 = {}
        for role in NN_ROLES:
            ga = [r for r in recs if r["role"] == role and is_canonical(r)]
            nn = [
                r
                for r in recs
                if r["role"] == role
                and r["method"] == "ga_nn"
                and r["ablation"] == "full"
                and r.get("truck_speed") is None
            ]
            if not ga or not nn:
                continue
            gaf = [r["best_fit"] for r in ga]
            nnf = [r["best_fit"] for r in nn]
            ga_gap = [ga_order_gap(role, r["best_order"], order_cache) for r in ga if r.get("best_order")]
            nn_gap = [ga_order_gap(role, r["best_order"], order_cache) for r in nn if r.get("best_order")]
            dcost = 100.0 * (mean(nnf) - mean(gaf)) / mean(gaf)
            md.append(
                f"| {role} | {N_BY_ROLE[role]} | {fmt_pm(gaf)} | {fmt_pm(nnf)} | {dcost:+.1f}% | "
                f"{mean(ga_gap):.1f}% | {mean(nn_gap):.1f}% |"
            )
            t7[role] = {
                "ga_mean": mean(gaf),
                "nn_mean": mean(nnf),
                "dcost_pct": dcost,
                "ga_order_gap": mean(ga_gap),
                "nn_order_gap": mean(nn_gap),
            }
        summary["nn_hybrid"] = t7
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
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    for ax, role in zip(axes, ["C3line", "C5mixed", "C10grid"]):
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
        ax.set_title(f"{role} (N={N_BY_ROLE[role]})")
        ax.set_xlabel("generation")
        ax.set_ylabel("best-so-far cost")
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
                and r["crossover"] == "ox"
                and r["mutation"] == "swap"
                and r.get("truck_speed") is None
            ]
            deltas.append(100.0 * (mean(ab) - mean(full)) / mean(full) if (ab and full) else 0)
        ax.bar(xs + (k - 1.5) * width, deltas, width, label=abl)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels(abl_roles)
    ax.set_ylabel("cost increase vs full GA (%)")
    ax.set_title("Ablation: how much each optimization dimension is worth")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig2_ablation.png", dpi=130)
    plt.close(fig)

    # Fig 3: Scaling — wall time and best_fit vs N
    roles_sorted = sorted(N_BY_ROLE, key=lambda x: N_BY_ROLE[x])
    Ns, walls, fits = [], [], []
    for role in roles_sorted:
        ga = [r for r in recs if r["role"] == role and is_canonical(r)]
        if not ga:
            continue
        Ns.append(N_BY_ROLE[role])
        walls.append(mean(r["wall_s"] for r in ga))
        fits.append(mean(r["best_fit"] for r in ga))
    if Ns:
        fig, ax1 = plt.subplots(figsize=(7, 4.5))
        ax1.plot(Ns, walls, "o-", color="C0", label="wall time (s)")
        ax1.set_xlabel("number of fields N")
        ax1.set_ylabel("wall time per run (s)", color="C0")
        ax2 = ax1.twinx()
        ax2.plot(Ns, fits, "s--", color="C2", label="best_fit")
        ax2.set_ylabel("best_fit (cost)", color="C2")
        ax1.set_title("Scaling with number of fields")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "fig3_scaling.png", dpi=130)
        plt.close(fig)

    # Fig 4: Transit-speed sensitivity
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, role in zip(axes, ["C5mixed", "C10grid"]):
        speeds = [(20.0, 20), (None, 40), (60.0, 60), (80.0, 80)]
        sx, sy_fit, sy_tr = [], [], []
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
                    and r["crossover"] == "ox"
                    and r["mutation"] == "swap"
                    and r.get("truck_speed") == ts_key
                ]
            if not rr:
                continue
            sx.append(disp)
            sy_fit.append(mean(r["best_fit"] for r in rr))
            sy_tr.append(mean(r["final"]["transit_time"] for r in rr))
        if sx:
            ax.plot(sx, sy_fit, "o-", color="C0", label="best_fit")
            ax.set_xlabel("truck speed (km/h)")
            ax.set_ylabel("best_fit", color="C0")
            axb = ax.twinx()
            axb.plot(sx, sy_tr, "s--", color="C3", label="transit (h)")
            axb.set_ylabel("transit (h)", color="C3")
            ax.set_title(f"{role}")
    fig.suptitle("Truck-speed sensitivity")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig4_transit.png", dpi=130)
    plt.close(fig)

    # Fig 5: TSP operator gap (C10grid) bar chart
    if tsp and "C10grid" in tsp:
        ops = tsp["C10grid"]["ops"]
        keys = [f"{c}_{m}" for c in ["ox", "pmx", "cx"] for m in ["swap", "insert", "inversion"]]
        gaps = [ops[k]["mean_gap_pct"] for k in keys]
        errs = [ops[k]["std_gap_pct"] for k in keys]
        fig, ax = plt.subplots(figsize=(10, 4.5))
        colors = ["C0" if "swap" in k else "C1" if "insert" in k else "C2" for k in keys]
        ax.bar(keys, gaps, yerr=errs, color=colors, capsize=3)
        ax.set_ylabel("mean optimality gap (%)")
        ax.set_title("Ordering operators on the C10grid TSP subproblem (vs Held-Karp optimum)")
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        fig.savefig(FIG_DIR / "fig5_tsp_operators.png", dpi=130)
        plt.close(fig)

    # Fig 6: NN-seeded hybrid — order-gap before/after (and NN optimum reference)
    if order_cache is not None and any(r["method"] == "ga_nn" for r in recs):
        roles = [r for r in NN_ROLES if any(x["role"] == r and x["method"] == "ga_nn" for x in recs)]
        ga_gaps, nn_gaps = [], []
        for role in roles:
            ga = [
                ga_order_gap(role, r["best_order"], order_cache)
                for r in recs
                if r["role"] == role and is_canonical(r) and r.get("best_order")
            ]
            nn = [
                ga_order_gap(role, r["best_order"], order_cache)
                for r in recs
                if r["role"] == role and r["method"] == "ga_nn" and r.get("best_order")
            ]
            ga_gaps.append(mean(ga) if ga else 0)
            nn_gaps.append(mean(nn) if nn else 0)
        xs = np.arange(len(roles))
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.bar(xs - 0.2, ga_gaps, 0.4, label="plain joint GA", color="C0")
        ax.bar(xs + 0.2, nn_gaps, 0.4, label="NN-seeded GA", color="C2")
        ax.set_xticks(xs)
        ax.set_xticklabels(roles)
        ax.set_ylabel("field-order gap vs optimal (%)")
        ax.set_title("NN-seeded hybrid removes the GA's ordering deficit")
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIG_DIR / "fig6_nn_hybrid.png", dpi=130)
        plt.close(fig)


if __name__ == "__main__":
    main()
