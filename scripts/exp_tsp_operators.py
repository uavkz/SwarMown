"""Operator comparison on the field-ordering subproblem (pure open-path TSP).

Field ordering only influences campaign cost through transit, and that transit
is a tiny ($-) lever relative to coverage cost -- so comparing ordering
operators by *joint* cost is mostly noise. Here we isolate the operators on
their actual job: minimise the open-path transit tour over the campaign's
directed transit matrix, using the EXACT same crossover (OX/PMX/CX) and mutation
(swap/insert/inversion) operators as the full multi-field GA, and measure how
close each reaches the Held-Karp optimum.

This is the honest, high-signal operator comparison. Runs in seconds (no field
routing) so we can afford many seeds.

Run: venv39\\Scripts\\python.exe scripts/exp_tsp_operators.py
"""

import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
import django

django.setup()

from scripts.exp_ordering import held_karp, nn_order, tour_cost, transit_matrix  # noqa: E402
from scripts.ga_multi_common import (  # noqa: E402
    cx_cycle,
    cx_order,
    cx_pmx,
    cx_rk_uniform,
    decode_order,
    mut_insert,
    mut_inversion,
    mut_rk,
    mut_swap,
)

CX = {"ox": cx_order, "pmx": cx_pmx, "cx": cx_cycle, "rk": cx_rk_uniform}
MUT = {"swap": mut_swap, "insert": mut_insert, "inversion": mut_inversion, "rk": mut_rk}

CROSSOVERS = ["ox", "pmx", "cx"]
MUTATIONS = ["swap", "insert", "inversion"]
# Evaluated pairs: the 3x3 permutation grid plus the random-keys encoding
# (uniform key crossover + Gaussian key mutation, decoded by argsort).
PAIRS = [(c, m) for c in CROSSOVERS for m in MUTATIONS] + [("rk", "rk")]


def tsp_ga(M, cx_name, mut_name, pop_size, ngen, mutation_chance, opt_cost, cxpb=0.5, mutpb=1.0):
    """Permutation-only GA mirroring the multi-field GA's varAnd dynamics.

    Individuals are [order] (1-element lists) so the shared cx_* operators,
    which act on ind[0], apply unchanged. Returns (best_cost, gap%, gen_hit).
    """
    n = len(M)
    cx_fn = CX[cx_name]
    mut_fn = MUT[mut_name]

    def fit(ind):
        return tour_cost(M, decode_order(ind[0]))

    if cx_name == "rk":
        pop = [[[random.random() for _ in range(n)]] for _ in range(pop_size)]
    else:
        pop = [[random.sample(range(n), n)] for _ in range(pop_size)]
    fits = [fit(ind) for ind in pop]
    best_cost = min(fits)
    gen_hit = None
    tol = max(1e-9, abs(opt_cost) * 1e-6)
    if best_cost - opt_cost <= tol:
        gen_hit = 0

    for g in range(ngen):
        offspring = [[ind[0][:]] for ind in pop]  # clone
        for i in range(1, pop_size, 2):  # mate (cxpb)
            if random.random() < cxpb:
                cx_fn(offspring[i - 1], offspring[i])
        for ind in offspring:  # mutate (mutpb=1; mut_fn gated by mutation_chance)
            if random.random() < mutpb:
                mut_fn(ind[0], mutation_chance)
        off_fits = [fit(o) for o in offspring]
        gen_best = min(off_fits)
        if gen_best < best_cost:
            best_cost = gen_best
        if gen_hit is None and best_cost - opt_cost <= tol:
            gen_hit = g + 1
        # (mu + lambda): size-3 tournament over parents + offspring (mirrors the
        # elitist survivor selection of the joint multi-field GA)
        combined = pop + offspring
        cfits = fits + off_fits
        nxt, nfits = [], []
        for _ in range(pop_size):
            a, b, c = (random.randrange(len(combined)) for _ in range(3))
            w = min((a, b, c), key=lambda k: cfits[k])
            nxt.append([combined[w][0][:]])
            nfits.append(cfits[w])
        pop, fits = nxt, nfits

    gap = 100.0 * (best_cost - opt_cost) / opt_cost if opt_cost > 1e-9 else 0.0
    return best_cost, gap, gen_hit


def main(seeds=30, pop=50, ngen=60, mutation_chance=0.1):
    from scripts.ga_multi_common import load_campaign

    manifest = json.loads((Path(__file__).resolve().parent / "exp_manifest.json").read_text(encoding="utf-8"))
    roles = ["C3line", "C3tri", "C5mixed", "C5holes", "C5varied", "C5size", "C10grid", "C15scatter"]  # N >= 3

    results = {}
    print(f"TSP operator study: seeds={seeds} pop={pop} ngen={ngen}\n")
    for ri, role in enumerate(roles):
        cd = load_campaign(manifest[role])
        M = transit_matrix(cd)
        n = cd["num_fields"]
        opt_cost, _ = held_karp(M, minimize=True)
        nn_cost = tour_cost(M, nn_order(M))
        results[role] = {"n": n, "opt": opt_cost, "nn": nn_cost, "ops": {}}
        print(f"=== {role} (N={n}) opt={opt_cost:.4f}h  NN={nn_cost:.4f}h ===")
        print(f"  {'operator':14s} {'mean_gap%':>9s} {'std_gap%':>8s} {'succ%':>6s} {'mean_gen_hit':>12s}")
        for pi, (cx, mut) in enumerate(PAIRS):
            gaps, hits, succ = [], [], 0
            for s in range(seeds):
                # deterministic, distinct seed per (role, operator, repeat)
                random.seed(((ri * len(PAIRS) + pi) * 10007 + s) + 1)
                _bc, gap, gen_hit = tsp_ga(M, cx, mut, pop, ngen, mutation_chance, opt_cost)
                gaps.append(gap)
                if gen_hit is not None:
                    succ += 1
                    hits.append(gen_hit)
            mean_gap = sum(gaps) / len(gaps)
            var = sum((x - mean_gap) ** 2 for x in gaps) / len(gaps)
            std_gap = var**0.5
            succ_pct = 100.0 * succ / seeds
            mean_hit = (sum(hits) / len(hits)) if hits else float("nan")
            key = f"{cx}_{mut}" if cx != "rk" else "rk"
            results[role]["ops"][key] = {
                "mean_gap_pct": mean_gap,
                "std_gap_pct": std_gap,
                "success_pct": succ_pct,
                "mean_gen_hit": mean_hit,
                "gaps": gaps,
            }
            print(f"  {key:14s} {mean_gap:9.2f} {std_gap:8.2f} {succ_pct:6.0f} {mean_hit:12.1f}")
        print()

    with open(Path(__file__).resolve().parent / "exp_tsp.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("-> scripts/exp_tsp.json")


if __name__ == "__main__":
    main()
