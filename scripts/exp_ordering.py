"""Ordering-subproblem analysis for multi-field campaigns.

Field ordering affects total campaign cost ONLY through transit time: each field
is routed independently, so per-drone cumulative flight time (a sum) and drone
price are order-invariant; only the truck transit between consecutive fields,
which feeds total_time = max_drone_time + transit, depends on the visit order.

This module builds the directed transit matrix per campaign and computes:
  * exact optimal open-path tour (Held-Karp DP, exact for N up to ~15),
  * exact worst open-path tour,
  * nearest-neighbour heuristic tour (best over all start fields),
  * default (as-given) order tour,
and the resulting cost "lever" = (worst-best) transit * hourly_price,
i.e. how many dollars the ordering decision is worth (one crew, paid per hour).

Importable: transit_matrix(cd), held_karp(M, minimize), nn_order(M),
tour_cost(M, order). Run directly to print a per-campaign table.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
import django

django.setup()


def transit_matrix(cd):
    """Directed transit-time matrix (hours): M[i][j] = field i -> field j."""
    from mainapp.utils import transit_time_hours

    fds = cd["fields_data"]
    speed = cd["campaign"].truck_speed_kmh
    n = len(fds)
    M = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                M[i][j] = transit_time_hours(fds[i]["road_latlon"], fds[j]["road_latlon"], speed)
    return M


def tour_cost(M, order):
    return sum(M[order[k]][order[k + 1]] for k in range(len(order) - 1))


def held_karp(M, minimize=True):
    """Exact optimal/worst open Hamiltonian path. Returns (cost, order)."""
    n = len(M)
    if n == 1:
        return 0.0, [0]
    better = min if minimize else max
    INF = float("inf") if minimize else float("-inf")
    # dp[mask][j] = best cost of a path covering `mask`, ending at j.
    dp = [[INF] * n for _ in range(1 << n)]
    parent = [[-1] * n for _ in range(1 << n)]
    for j in range(n):
        dp[1 << j][j] = 0.0
    for mask in range(1 << n):
        for j in range(n):
            if dp[mask][j] == INF or not (mask & (1 << j)):
                continue
            for k in range(n):
                if mask & (1 << k):
                    continue
                nmask = mask | (1 << k)
                cand = dp[mask][j] + M[j][k]
                if better(cand, dp[nmask][k]) == cand and cand != dp[nmask][k]:
                    dp[nmask][k] = cand
                    parent[nmask][k] = j
    full = (1 << n) - 1
    best_j, best_cost = -1, INF
    for j in range(n):
        if better(dp[full][j], best_cost) == dp[full][j]:
            best_cost = dp[full][j]
            best_j = j
    # reconstruct
    order = []
    mask, j = full, best_j
    while j != -1:
        order.append(j)
        pj = parent[mask][j]
        mask ^= 1 << j
        j = pj
    order.reverse()
    return best_cost, order


def nn_order(M):
    """Nearest-neighbour heuristic, best over all possible start fields."""
    n = len(M)
    best_cost, best_order = float("inf"), list(range(n))
    for start in range(n):
        visited = [False] * n
        order = [start]
        visited[start] = True
        for _ in range(n - 1):
            last = order[-1]
            nxt = min((j for j in range(n) if not visited[j]), key=lambda j: M[last][j])
            order.append(nxt)
            visited[nxt] = True
        c = tour_cost(M, order)
        if c < best_cost:
            best_cost, best_order = c, order
    return best_order


def main():
    from scripts.ga_multi_common import load_campaign

    manifest = json.loads((Path(__file__).resolve().parent / "exp_manifest.json").read_text(encoding="utf-8"))
    hourly = 10.0  # campaigns share hourly_price=10
    print(
        f"{'role':9s} {'N':>2s} {'opt_h':>7s} {'nn_h':>7s} {'dflt_h':>7s} {'worst_h':>8s} "
        f"{'nn_gap%':>7s} {'dflt_gap%':>9s} {'lever$':>12s}"
    )
    out = {}
    for role, cid in manifest.items():
        cd = load_campaign(cid)
        n = cd["num_fields"]
        M = transit_matrix(cd)
        opt_c, opt_o = held_karp(M, minimize=True)
        worst_c, _ = held_karp(M, minimize=False)
        nn_o = nn_order(M)
        nn_c = tour_cost(M, nn_o)
        dflt_o = list(range(n))
        dflt_c = tour_cost(M, dflt_o)
        nn_gap = 100 * (nn_c - opt_c) / opt_c if opt_c > 0 else 0
        dflt_gap = 100 * (dflt_c - opt_c) / opt_c if opt_c > 0 else 0
        lever = (worst_c - opt_c) * hourly  # crew is paid per hour (one crew, any fleet)
        print(
            f"{role:9s} {n:2d} {opt_c:7.3f} {nn_c:7.3f} {dflt_c:7.3f} {worst_c:8.3f} "
            f"{nn_gap:7.1f} {dflt_gap:9.1f} {lever:12.2f}"
        )
        out[role] = {
            "n": n,
            "opt": opt_c,
            "nn": nn_c,
            "default": dflt_c,
            "worst": worst_c,
            "opt_order": opt_o,
            "nn_order": nn_o,
            "nn_gap_pct": nn_gap,
            "default_gap_pct": dflt_gap,
        }
    with open(Path(__file__).resolve().parent / "exp_ordering.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
