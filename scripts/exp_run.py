"""Multi-field experiment harness.

Runs a deduplicated matrix of GA / random-search jobs against the campaigns
created by exp_campaigns.py. Each job is one serial GA (or random search) run;
jobs are parallelised across processes (one GA per core) rather than
parallelising fitness within a run -- evaluations are cheap (~10-100 ms) so this
gives far better throughput and lets us run many seeds for statistics.

Design notes:
  * The GA has no elitism (pure tournament on offspring), so a best individual
    can be lost between generations. We therefore report best-of-run via a
    hall-of-fame and a monotone best-so-far convergence curve (standard
    practice), without altering the GA dynamics.
  * Random search (RS) uses the same evaluation budget (ngen*pop) as the GA and
    records best-so-far every `pop` samples, so its curve is directly
    comparable to a GA generation axis.
  * RNG is seeded per job for reproducibility.

Output: one JSON object per line in --out (default scripts/exp_results.jsonl),
appended as jobs finish (crash-robust).

Run:
    venv39\\Scripts\\python.exe scripts/exp_run.py --ngen 30 --pop 50 --seeds 8 --workers 8
    venv39\\Scripts\\python.exe scripts/exp_run.py --smoke   # tiny sanity run
"""

import argparse
import contextlib
import io
import json
import math
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
import django

django.setup()

from concurrent.futures import ProcessPoolExecutor, as_completed  # noqa: E402

from pyproj import Transformer  # noqa: E402

from scripts.ga_multi_common import (  # noqa: E402
    evaluate_multi_individual,
    generate_multi_individual,
    mutate_multi,
    setup_multi_toolbox,
)

MANIFEST = json.loads((Path(__file__).resolve().parent / "exp_manifest.json").read_text(encoding="utf-8"))

# Per-worker caches (populated lazily in each process).
_TRANSFORMER = None
_CAMPAIGN_CACHE = {}
_NN_CACHE = {}


class _Args:
    """Lightweight stand-in for the argparse namespace evaluate_* expects."""

    def __init__(self, max_working_speed, borderline_time, max_time, truck_speed, mutation_chance):
        self.max_working_speed = max_working_speed
        self.borderline_time = borderline_time
        self.max_time = max_time
        self.truck_speed = truck_speed
        self.mutation_chance = mutation_chance


def _transformer():
    global _TRANSFORMER
    if _TRANSFORMER is None:
        _TRANSFORMER = Transformer.from_crs("epsg:4087", "epsg:4326", always_xy=True)
    return _TRANSFORMER


def _campaign(cid):
    if cid not in _CAMPAIGN_CACHE:
        from scripts.ga_multi_common import load_campaign

        _CAMPAIGN_CACHE[cid] = load_campaign(cid)
    return _CAMPAIGN_CACHE[cid]


def _components(res):
    # Coerce numpy scalars to native Python types for JSON.
    distance, t, drone_price, salary, penalty, starts, transit, grid_total, grid_missed, drone_usage = res
    return {
        "distance": round(float(distance), 4),
        "time": round(float(t), 4),
        "drone_price": round(float(drone_price), 4),
        "salary": round(float(salary), 4),
        "penalty": round(float(penalty), 4),
        "starts": int(starts),
        "transit_time": round(float(transit), 4),
        "grid_total": int(grid_total),
        "grid_missed": int(grid_missed),
        "covered_ok": bool(grid_missed == 0),
        "drone_usage": {str(k): [int(v[0]), round(float(v[1]), 4)] for k, v in drone_usage.items()},
    }


def _nn_order_for(cd):
    """Nearest-neighbour field order from the transit matrix (cached)."""
    cid = cd["campaign"].id
    if cid not in _NN_CACHE:
        from scripts.exp_ordering import nn_order, transit_matrix

        _NN_CACHE[cid] = nn_order(transit_matrix(cd))
    return _NN_CACHE[cid]


def _run_ga(cd, args, crossover, mutation, ablation, ngen, pop, seed_order=None):
    from deap import algorithms

    tr = _transformer()

    def ev(ind):
        return evaluate_multi_individual(ind, cd, args, tr)

    def mut(ind):
        return mutate_multi(
            ind,
            cd["num_drones"],
            cd["num_fields"],
            args.mutation_chance,
            order_mutation=mutation,
            ablation=ablation,
        )

    # setup_multi_toolbox registers scoop's futures.map; force serial map.
    with contextlib.redirect_stdout(io.StringIO()):
        tb = setup_multi_toolbox(
            cd["num_fields"], cd["num_drones"], ev, mut, crossover_type=crossover, ablation=ablation
        )
    tb.register("map", map)

    population = tb.population(n=pop)
    if seed_order is not None:
        # Initialise every individual's order gene with the nearest-neighbour
        # tour. Callers pair this with ablation="fixed_order" so the order stays
        # frozen at the NN tour and the budget goes to the coverage parameters.
        for ind in population:
            ind[0] = list(seed_order)
    best_fit = math.inf
    best_ind = None
    best_res = None
    curve = []

    def score(ind):
        nonlocal best_fit, best_ind, best_res
        res = ev(ind)
        total = res[2] + res[3] + res[4]
        ind.fitness.values = (total,)
        if total < best_fit:
            best_fit = total
            best_ind = tb.clone(ind)
            best_res = res

    # (mu + lambda) evolution with survivor selection over parents+offspring:
    # the legacy comma scheme (select over offspring only, mutpb=1, no elitism)
    # loses its best individual almost every generation and stalls. Evaluating
    # the initial population counts toward the budget, so the total number of
    # evaluations is exactly ngen*pop -- identical to random search.
    for ind in population:
        score(ind)
    curve.append(best_fit)
    for _gen in range(ngen - 1):
        offspring = algorithms.varAnd(population, tb, cxpb=0.5, mutpb=1)
        for ind in offspring:
            score(ind)
        population = tb.select(population + offspring, k=len(population))
        curve.append(best_fit)
    return best_fit, curve, best_ind, best_res, ngen * pop


def _run_rs(cd, args, ngen, pop):
    tr = _transformer()
    budget = ngen * pop
    best_fit = math.inf
    best_ind = None
    best_res = None
    curve = []
    for i in range(budget):
        ind = generate_multi_individual(cd["num_fields"], cd["num_drones"])
        res = evaluate_multi_individual(ind, cd, args, tr)
        total = res[2] + res[3] + res[4]
        if total < best_fit:
            best_fit = total
            best_ind = ind
            best_res = res
        if (i + 1) % pop == 0:
            curve.append(best_fit)
    return best_fit, curve, best_ind, best_res, budget


def run_one(job):
    """Execute a single job. Returns a result dict (picklable).

    The RNG is seeded with the full job identity (not just the seed index), so
    e.g. GA seed 0 and RS seed 0 consume independent random streams — otherwise
    the GA's initial population and RS's first `pop` samples would be identical
    (common random numbers), undermining the independence assumption of the
    Mann-Whitney comparison.
    """
    random.seed(
        f"{job['role']}|{job['method']}|{job['crossover']}|{job['mutation']}"
        f"|{job['ablation']}|{job.get('truck_speed')}|{job['seed']}"
    )
    cd = _campaign(job["campaign_id"])
    args = _Args(
        max_working_speed=job["max_working_speed"],
        borderline_time=job["borderline_time"],
        max_time=job["max_time"],
        truck_speed=job.get("truck_speed"),
        mutation_chance=job["mutation_chance"],
    )
    t0 = time.time()
    if job["method"] == "rs":
        best_fit, curve, best_ind, best_res, n_evals = _run_rs(cd, args, job["ngen"], job["pop"])
    else:
        if job["method"] == "ga_nn":
            # NN-fixed hybrid: freeze the order gene at the nearest-neighbour tour
            # and spend the whole GA budget on the per-field coverage parameters.
            seed_order = _nn_order_for(cd)
            ablation = "fixed_order"
        else:
            seed_order = None
            ablation = job["ablation"]
        best_fit, curve, best_ind, best_res, n_evals = _run_ga(
            cd,
            args,
            job["crossover"],
            job["mutation"],
            ablation,
            job["ngen"],
            job["pop"],
            seed_order=seed_order,
        )
    wall = time.time() - t0

    rec = dict(job)
    rec["n_evals"] = n_evals
    rec["wall_s"] = round(wall, 2)
    rec["best_fit"] = round(float(best_fit), 4)
    rec["curve"] = [round(float(c), 3) for c in curve]
    rec["final"] = _components(best_res)
    if best_ind is not None:
        from scripts.ga_multi_common import decode_order

        rec["best_order"] = [int(x) for x in decode_order(best_ind[0])]
        rec["best_ind"] = {
            "order_gene": [round(float(x), 6) for x in best_ind[0]]
            if best_ind[0] and isinstance(best_ind[0][0], float)
            else [int(x) for x in best_ind[0]],
            "directions": [round(float(d), 2) for d in best_ind[1]],
            "starts": list(best_ind[2]),
            "drones": [[int(i) for i in dl] for dl in best_ind[3]],
            "car_points": [[round(float(c), 4) for c in cp] for cp in best_ind[4]],
        }
    else:
        rec["best_order"] = None
        rec["best_ind"] = None
    return rec


# --- Job matrix -------------------------------------------------------------

ALL_ROLES = [
    "C2close",
    "C2far",
    "C3line",
    "C3tri",
    "C3big",
    "C5mixed",
    "C5holes",
    "C10grid",
    "C5varied",
    "C5size",
    "C15scatter",
]
# Joint operator grid only on the most ordering-sensitive campaign (robustness
# check); the clean operator comparison lives in exp_tsp_operators.py.
OP_ROLES = ["C10grid"]
# Random-keys order encoding vs the canonical permutation encoding, on the two
# campaigns with a real combinatorial tour space.
ENC_ROLES = ["C10grid", "C15scatter"]
# Ablation on a spread of regimes: C3line (default order already optimal -> the
# fixed_order ablation should be harmless), C5holes & C10grid (default order is
# far worse than optimal -> fixed_order should hurt), C5mixed (in between),
# C5varied (elongated fields at different orientations -> per-field direction
# genuinely matters), C5size (field sizes differ 16x -> per-field drone subsets
# genuinely matter), C3big (very large fields -> within-field parallelism via the
# drones gene is the dominant lever; single_drones is the money ablation).
ABL_ROLES = ["C3line", "C5mixed", "C5holes", "C10grid", "C5varied", "C5size", "C3big"]
# Campaigns where the field tour is a real combinatorial problem -> where the
# NN-fixed hybrid is worth comparing against the plain GA.
NN_ROLES = ["C5mixed", "C5holes", "C10grid", "C5varied", "C5size", "C15scatter"]
# Transit-speed sweep on C5mixed (clean grouping campaign); C10grid transit adds
# little and is the most expensive campaign, so we omit it from the sweep.
TRANSIT_ROLES = ["C5mixed"]
# The joint operator grid is only a robustness check (the honest operator
# comparison is the exact-TSP study); run it on few seeds to save compute.
OP_SEEDS = 3

CROSSOVERS = ["ox", "pmx", "cx"]
MUTATIONS = ["swap", "insert", "inversion"]
ABLATIONS = ["fixed_order", "single_direction", "single_start", "single_drones"]  # 'full' is canonical
TRANSIT_SPEEDS = [20.0, 60.0, 80.0]  # 40 is canonical


def build_jobs(
    ngen,
    pop,
    seeds,
    base_kwargs,
    roles_filter=None,
    nn_seed=False,
    nn_only=False,
    transit_roles=None,
    transit_only=False,
):
    jobs = []
    seen = set()

    def want(role):
        return role in MANIFEST and (roles_filter is None or role in roles_filter)

    def add(role, method, crossover, mutation, ablation, truck_speed, seed):
        if not want(role):
            return
        key = (role, method, crossover, mutation, ablation, truck_speed, seed)
        if key in seen:
            return
        seen.add(key)
        job = dict(base_kwargs)
        job.update(
            role=role,
            campaign_id=MANIFEST[role],
            method=method,
            crossover=crossover,
            mutation=mutation,
            ablation=ablation,
            truck_speed=truck_speed,
            seed=seed,
            ngen=ngen,
            pop=pop,
        )
        jobs.append(job)

    transit_roles = transit_roles or TRANSIT_ROLES

    for s in range(seeds):
        if transit_only:
            for role in transit_roles:
                for spd in TRANSIT_SPEEDS:
                    add(role, "ga", "ox", "inversion", "full", spd, s)
            continue
        if not nn_only:
            # (1) Canonical GA (full, ox+inversion — the recommended operator pair,
            # see Table 5) on every campaign -> scaling + baselines + anchors
            for role in ALL_ROLES:
                add(role, "ga", "ox", "inversion", "full", None, s)
            # (1b) Random-search baseline, matched budget, every campaign
            for role in ALL_ROLES:
                add(role, "rs", "ox", "inversion", "full", None, s)
            # (2) Operator grid (minus ox+inversion which is canonical), few seeds only
            if s < OP_SEEDS:
                for role in OP_ROLES:
                    for cx in CROSSOVERS:
                        for mut in MUTATIONS:
                            if cx == "ox" and mut == "inversion":
                                continue
                            add(role, "ga", cx, mut, "full", None, s)
            # (2b) Random-keys order encoding, full seeds (the headline encoding
            # comparison; the pure-TSP encoding study lives in exp_tsp_operators)
            for role in ENC_ROLES:
                add(role, "ga", "rk", "rk", "full", None, s)
            # (3) Ablations (full is canonical)
            for role in ABL_ROLES:
                for abl in ABLATIONS:
                    add(role, "ga", "ox", "inversion", abl, None, s)
            # (4) Transit-speed sensitivity (40 is canonical)
            for role in transit_roles:
                for spd in TRANSIT_SPEEDS:
                    add(role, "ga", "ox", "inversion", "full", spd, s)
        # (5) NN-fixed hybrid: order gene frozen at the NN tour (recorded as
        # ablation=fixed_order, which is what actually runs)
        if nn_seed or nn_only:
            for role in NN_ROLES:
                add(role, "ga_nn", "ox", "inversion", "fixed_order", None, s)

    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ngen", type=int, default=30)
    ap.add_argument("--pop", type=int, default=50)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=str, default=str(Path(__file__).resolve().parent / "exp_results.jsonl"))
    ap.add_argument("--max_working_speed", type=float, default=7)
    # Campaign-scale working-day limits: soft overtime penalty beyond 8 h,
    # hard limit 14 h. (The single-field defaults 4/12 are too tight for a
    # sequential multi-field campaign, whose duration is the sum of per-field
    # makespans plus transit.)
    ap.add_argument("--borderline_time", type=float, default=8)
    ap.add_argument("--max_time", type=float, default=14)
    ap.add_argument("--mutation_chance", type=float, default=0.1)
    ap.add_argument("--smoke", action="store_true", help="tiny run: 2 seeds, ngen=5, pop=10, 4 campaigns")
    ap.add_argument("--roles", type=str, default=None, help="comma-separated subset of campaign roles")
    ap.add_argument("--nn_seed", action="store_true", help="also run NN-seeded hybrid jobs on ordering-sensitive roles")
    ap.add_argument("--nn_only", action="store_true", help="run ONLY NN-seeded hybrid jobs (no full matrix)")
    ap.add_argument("--transit_roles", type=str, default=None, help="comma-separated roles for the truck-speed sweep")
    ap.add_argument("--transit_only", action="store_true", help="run ONLY truck-speed sweep jobs (no full matrix)")
    ap.add_argument(
        "--resume",
        action="store_true",
        help="append to --out, skipping jobs whose (role,method,cx,mut,ablation,speed,seed) is already present",
    )
    args = ap.parse_args()

    base_kwargs = dict(
        max_working_speed=args.max_working_speed,
        borderline_time=args.borderline_time,
        max_time=args.max_time,
        mutation_chance=args.mutation_chance,
    )

    if args.smoke:
        ngen, pop, seeds = 5, 10, 2
        jobs = []
        for s in range(seeds):
            for role in ["C2close", "C3line", "C5holes", "C10grid"]:
                for method in ["ga", "rs"]:
                    j = dict(base_kwargs)
                    j.update(
                        role=role,
                        campaign_id=MANIFEST[role],
                        method=method,
                        crossover="ox",
                        mutation="inversion",
                        ablation="full",
                        truck_speed=None,
                        seed=s,
                        ngen=ngen,
                        pop=pop,
                    )
                    jobs.append(j)
    else:
        roles_filter = [r.strip() for r in args.roles.split(",")] if args.roles else None
        jobs = build_jobs(
            args.ngen,
            args.pop,
            args.seeds,
            base_kwargs,
            roles_filter=roles_filter,
            nn_seed=args.nn_seed,
            nn_only=args.nn_only,
            transit_roles=[r.strip() for r in args.transit_roles.split(",")] if args.transit_roles else None,
            transit_only=args.transit_only,
        )

    out_path = Path(args.out)
    mode = "w"
    if args.resume and out_path.exists():
        done_keys = set()
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if "error" in r:
                    continue
                done_keys.add(
                    (
                        r["role"],
                        r["method"],
                        r["crossover"],
                        r["mutation"],
                        r["ablation"],
                        r.get("truck_speed"),
                        r["seed"],
                    )
                )
        before = len(jobs)
        jobs = [
            j
            for j in jobs
            if (j["role"], j["method"], j["crossover"], j["mutation"], j["ablation"], j.get("truck_speed"), j["seed"])
            not in done_keys
        ]
        mode = "a"
        print(f"resume: {before - len(jobs)} jobs already done, {len(jobs)} remaining")

    print(f"Total jobs: {len(jobs)}  workers={args.workers}  -> {out_path}")
    t0 = time.time()
    done = 0
    with open(out_path, mode, encoding="utf-8") as fout, ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one, j): j for j in jobs}
        for fut in as_completed(futs):
            try:
                rec = fut.result()
            except Exception as e:
                j = futs[fut]
                rec = {**j, "error": repr(e)}
                print(f"  ERROR {j['role']} {j['method']} seed={j['seed']}: {e!r}")
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()
            done += 1
            if done % 10 == 0 or done == len(jobs):
                el = time.time() - t0
                rate = done / el
                eta = (len(jobs) - done) / rate if rate else 0
                print(f"  {done}/{len(jobs)}  elapsed={el:6.0f}s  rate={rate:4.2f}/s  eta={eta:5.0f}s")
    print(f"DONE {len(jobs)} jobs in {time.time() - t0:.0f}s -> {out_path}")


if __name__ == "__main__":
    main()
