"""GA optimizer for missions with holes (2-stage: pre-evaluate decompositions, then GA)."""

import datetime
import json
import random
from concurrent.futures import ThreadPoolExecutor

from scripts.ga_common import (
    bootstrap_django,
    build_argparser,
    build_avoidance_config,
    custom_mutate,
    evaluate_individual,
    load_mission,
    make_pyproj_transformer,
    parse_obstacle_heights,
    run_ga,
    save_results,
    setup_toolbox,
)

bootstrap_django()

args = build_argparser().parse_args()
mission_data = load_mission(args.mission_id)
pyproj_transformer = make_pyproj_transformer()

# 3D avoidance setup
num_holes = len(mission_data["holes"])
hole_heights = parse_obstacle_heights(args, num_holes)
avoidance_config = build_avoidance_config(args, hole_heights) if args.avoidance_strategy != "2d" else None

NUM_RANDOM_INDIVS = 10
NUM_RANDOM_REQUIREMENTS = 30

BEST_REQS = None


def evaluate(individual):
    return evaluate_individual(
        individual,
        mission_data,
        args,
        pyproj_transformer,
        triangulation_requirements=BEST_REQS,
        avoidance_config=avoidance_config,
    )


def mutate(ind):
    return custom_mutate(ind, mission_data["num_drones"], args.mutation_chance, args.avoidance_strategy)


toolbox = setup_toolbox(
    mission_data["num_drones"],
    evaluate,
    mutate,
    avoidance_strategy=args.avoidance_strategy,
    num_holes=num_holes,
)


def _generate_random_requirements_sets(n):
    from pode import Requirement

    holes = json.loads(mission_data["mission"].field.holes_serialized)
    sets_ = []
    for _ in range(n):
        total = 1.0
        count = random.randint(len(holes) + 1, len(holes) * 2)
        vals = []
        for _ in range(count - 1):
            val = random.uniform(0, total)
            total -= val
            vals.append(val)
        vals.append(total)
        random.shuffle(vals)
        sets_.append([Requirement(v) for v in vals])
    return sets_


def _generate_random_individual():
    n = mission_data["num_drones"]
    return [
        random.uniform(0, 360),
        random.choice(["ne", "nw", "se", "sw"]),
        [random.randint(0, n - 1) for _ in range(random.randint(1, n * 3))],
        [random.uniform(0, 1) for _ in range(random.randint(1, 5))],
    ]


def _pre_eval_worker(combo):
    indiv, reqs = combo
    _, _, _dprice, _sal, _pen, _ = evaluate_individual(
        indiv,
        mission_data,
        args,
        pyproj_transformer,
        triangulation_requirements=reqs,
        avoidance_config=avoidance_config,
    )
    return {
        "cost": _dprice + _sal + _pen,
        "req": reqs,
    }


def run():
    global BEST_REQS

    # Stage 1: find best triangulation requirements
    req_sets = _generate_random_requirements_sets(NUM_RANDOM_REQUIREMENTS)
    random_inds = [_generate_random_individual() for _ in range(NUM_RANDOM_INDIVS)]
    combos = [(ind, req) for ind in random_inds for req in req_sets]

    print("Finding best requirements set...", datetime.datetime.now())
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(_pre_eval_worker, combos))

    best_preeval = min(results, key=lambda x: x["cost"])
    BEST_REQS = best_preeval["req"]
    print("Best requirements set found.", datetime.datetime.now())

    # Stage 2: main GA
    iterations = run_ga(toolbox, args.population_size, args.ngen)
    save_results(iterations, args, mission_data["mission"], best_reqs=BEST_REQS)


if __name__ == "__main__":
    run()
