"""Shared logic for multi-field (campaign) genetic algorithm scripts.

Contains: argument parsing, campaign loading, individual generation,
ordering crossover/mutation operators, evaluation, DEAP toolbox setup,
GA loop, and result saving.
"""

import json
import random
from collections import defaultdict

from scripts.ga_common import (
    _WP_LAT,
    _WP_LON,
    _WP_MAX_SPEED,
    _WP_MIN_SLOWDOWN,
    _WP_SLOWDOWN,
    _WP_SPRAY,
    MAX_DRONES_ON_CAR,
    SETUP_TIME_PER_FLIGHT_HOURS,
    TARGET_WEIGHTS,
    bootstrap_django,  # noqa: F401 — re-exported for genetic_multi.py
    make_pyproj_transformer,  # noqa: F401 — re-exported
)

# Cap on truck stops per field. More launch positions than this give no
# practical benefit (each stop costs start_price and a return leg) and only
# bloat evaluation cost, so we clamp both generation and mutation. 5 matches the
# generation upper bound, so generation and mutation stay consistent.
MAX_CAR_POINTS = 5

# mainapp imports are deferred to function bodies because Django must
# be bootstrapped first (bootstrap_django() hasn't been called yet
# when this module is imported at script startup).

# --- Argument parsing -------------------------------------------------------


def build_multi_argparser():
    """Create argument parser for multi-field GA scripts."""
    import argparse

    parser = argparse.ArgumentParser(description="Multi-field GA optimizer")
    parser.add_argument("--campaign_id", type=int, required=True)
    parser.add_argument("--ngen", type=int, default=25)
    parser.add_argument("--population_size", type=int, default=50)
    parser.add_argument("--filename", type=str, default="multi_test")
    parser.add_argument("--max-time", dest="max_time", type=float, default=12)
    parser.add_argument("--borderline_time", type=float, default=4)
    parser.add_argument("--max_working_speed", type=float, default=7)
    parser.add_argument("--mutation_chance", type=float, default=0.1)
    parser.add_argument("--truck_speed", type=float, default=None, help="Override campaign truck_speed_kmh")
    # "rk" selects random-keys order encoding (uniform key crossover + Gaussian
    # key mutation); use it for BOTH --order_crossover and --order_mutation.
    parser.add_argument("--order_crossover", type=str, default="ox", choices=["ox", "pmx", "cx", "rk"])
    # inversion (a 2-opt-like move) reaches the exact TSP optimum far more often than swap on
    # larger tours; see experiments/multi_field_results.md (Table 5) for the comparison.
    parser.add_argument(
        "--order_mutation", type=str, default="inversion", choices=["swap", "insert", "inversion", "rk"]
    )
    parser.add_argument(
        "--ablation",
        type=str,
        default="full",
        choices=[
            "full",
            "fixed_order",
            "fixed_direction",
            "fixed_start",
            "fixed_drones",
            "single_direction",
            "single_start",
            "single_drones",
        ],
    )
    return parser


# --- Campaign loading -------------------------------------------------------


def load_campaign(campaign_id):
    """Load Campaign, all fields, roads, holes, and drones from DB."""
    from mainapp.models import Campaign

    campaign = Campaign.objects.get(id=campaign_id)
    campaign_fields = campaign.campaign_fields.select_related("field").order_by("default_order")
    drones_list = list(campaign.drones.all().order_by("id"))

    fields_data = []
    for cf in campaign_fields:
        field_obj = cf.field
        field = [[y, x] for x, y in json.loads(field_obj.points_serialized)]
        road = [[y, x] for x, y in json.loads(field_obj.road_serialized)]
        road_latlon = json.loads(field_obj.road_serialized)
        holes_raw = json.loads(field_obj.holes_serialized)
        holes = [[[y, x] for x, y in hole] for hole in holes_raw if len(hole) >= 3]

        fields_data.append(
            {
                "field_obj": field_obj,
                "field": field,
                "road": road,
                "road_latlon": road_latlon,
                "holes": holes,
            }
        )

    return {
        "campaign": campaign,
        "fields_data": fields_data,
        "drones_list": drones_list,
        "num_drones": len(drones_list),
        "num_fields": len(fields_data),
    }


# --- Individual generation --------------------------------------------------


def decode_order(gene):
    """Decode the order gene to a visit permutation.

    Permutation encoding stores the permutation directly (list of ints);
    random-keys encoding stores one float key per field and visits fields in
    ascending key order (argsort).
    """
    if gene and isinstance(gene[0], float):
        return sorted(range(len(gene)), key=lambda i: gene[i])
    return gene


def generate_multi_individual(num_fields, num_drones, ablation="full", order_encoding="perm"):
    """Generate a random multi-field individual.

    Individual structure:
        [0] field_order:    list[int] (permutation of 0..N-1) or, with
                            order_encoding="rk", list[float] random keys
                            decoded via argsort at evaluation time
        [1] directions:     list[float]       — direction per field (indexed by field_idx)
        [2] starts:         list[str]         — start corner per field
        [3] drones:         list[list[int]]   — drone indices per field
        [4] car_points:     list[list[float]] — car stop ratios per field
    """
    if num_drones < 1:
        num_drones = 1
    if num_fields < 1:
        num_fields = 1

    # Field order
    if ablation == "fixed_order":
        field_order = list(range(num_fields))
    elif order_encoding == "rk":
        field_order = [random.random() for _ in range(num_fields)]
    else:
        field_order = list(range(num_fields))
        random.shuffle(field_order)

    # Direction
    if ablation == "single_direction":
        d = random.uniform(0, 360)
        directions = [d] * num_fields
    elif ablation == "fixed_direction":
        # Not optimized: east-west flight lines everywhere (naive default).
        directions = [0.0] * num_fields
    else:
        directions = [random.uniform(0, 360) for _ in range(num_fields)]

    # Start corner
    if ablation == "single_start":
        s = random.choice(["ne", "nw", "se", "sw"])
        starts = [s] * num_fields
    elif ablation == "fixed_start":
        # Not optimized: corner nearest the road's western entry (naive default).
        starts = ["sw"] * num_fields
    else:
        starts = [random.choice(["ne", "nw", "se", "sw"]) for _ in range(num_fields)]

    # Drones per field (length capped at MAX_DRONES_ON_CAR so generation and
    # mutation sample the same space)
    max_len = min(num_drones * 3, MAX_DRONES_ON_CAR)
    if ablation == "single_drones":
        shared = [random.randint(0, num_drones - 1) for _ in range(random.randint(1, max_len))]
        drones = [shared[:] for _ in range(num_fields)]
    elif ablation == "fixed_drones":
        # Fleet not optimized: a single mid-class workhorse covers every field
        # (the reasonable naive default -- also the best single model overall).
        drones = [[num_drones // 2] for _ in range(num_fields)]
    else:
        drones = [
            [random.randint(0, num_drones - 1) for _ in range(random.randint(1, max_len))] for _ in range(num_fields)
        ]

    # Car points per field
    car_points = [sorted([random.uniform(0, 1) for _ in range(random.randint(1, 5))]) for _ in range(num_fields)]

    return [field_order, directions, starts, drones, car_points]


# --- Ordering crossover operators -------------------------------------------


def cx_order(ind1, ind2):
    """Order Crossover (OX) on field_order gene.

    Copies a random segment from parent1 into child1, fills remaining
    positions from parent2 in order (preserving relative sequence).
    """
    order1, order2 = ind1[0], ind2[0]
    size = len(order1)
    if size < 2:
        return ind1, ind2

    a, b = sorted(random.sample(range(size), 2))

    child1 = [None] * size
    child1[a : b + 1] = order1[a : b + 1]
    segment1 = set(child1[a : b + 1])
    fill = [x for x in order2 if x not in segment1]
    j = 0
    for i in range(size):
        if child1[i] is None:
            child1[i] = fill[j]
            j += 1

    child2 = [None] * size
    child2[a : b + 1] = order2[a : b + 1]
    segment2 = set(child2[a : b + 1])
    fill = [x for x in order1 if x not in segment2]
    j = 0
    for i in range(size):
        if child2[i] is None:
            child2[i] = fill[j]
            j += 1

    ind1[0], ind2[0] = child1, child2
    return ind1, ind2


def cx_pmx(ind1, ind2):
    """Partially Mapped Crossover (PMX) on field_order gene.

    Swaps a segment between parents and resolves conflicts via mapping.
    """
    order1, order2 = ind1[0][:], ind2[0][:]
    size = len(order1)
    if size < 2:
        return ind1, ind2

    a, b = sorted(random.sample(range(size), 2))

    mapping1, mapping2 = {}, {}
    for i in range(a, b + 1):
        mapping1[order2[i]] = order1[i]
        mapping2[order1[i]] = order2[i]

    child1, child2 = order1[:], order2[:]
    child1[a : b + 1] = order2[a : b + 1]
    child2[a : b + 1] = order1[a : b + 1]

    seg2 = set(order2[a : b + 1])
    seg1 = set(order1[a : b + 1])

    for i in list(range(0, a)) + list(range(b + 1, size)):
        for _ in range(size):  # cycle guard
            if child1[i] not in seg2:
                break
            child1[i] = mapping1[child1[i]]
        for _ in range(size):
            if child2[i] not in seg1:
                break
            child2[i] = mapping2[child2[i]]

    ind1[0], ind2[0] = child1, child2
    return ind1, ind2


def cx_cycle(ind1, ind2):
    """Cycle Crossover (CX) on field_order gene.

    Identifies cycles between parents and copies alternating cycles.
    """
    order1, order2 = ind1[0], ind2[0]
    size = len(order1)
    if size < 2:
        return ind1, ind2

    child1, child2 = [None] * size, [None] * size
    visited = [False] * size
    cycle_num = 0

    for start in range(size):
        if visited[start]:
            continue
        idx = start
        while not visited[idx]:
            visited[idx] = True
            if cycle_num % 2 == 0:
                child1[idx] = order1[idx]
                child2[idx] = order2[idx]
            else:
                child1[idx] = order2[idx]
                child2[idx] = order1[idx]
            idx = order1.index(order2[idx])
        cycle_num += 1

    # Safety: fill any None gaps (shouldn't happen, but guard)
    for i in range(size):
        if child1[i] is None:
            child1[i] = order1[i]
        if child2[i] is None:
            child2[i] = order2[i]

    ind1[0], ind2[0] = child1, child2
    return ind1, ind2


def cx_per_field_params(ind1, ind2, num_fields):
    """Uniform swap crossover on per-field parameters (genes 1-4).

    For each field, independently swap all per-field genes with 50% probability.
    """
    for field_idx in range(num_fields):
        if random.random() < 0.5:
            for gene_idx in [1, 2, 3, 4]:
                ind1[gene_idx][field_idx], ind2[gene_idx][field_idx] = (
                    ind2[gene_idx][field_idx],
                    ind1[gene_idx][field_idx],
                )
    return ind1, ind2


# --- Ordering mutation operators --------------------------------------------


def mut_swap(order, mutation_chance):
    """Swap two random positions in the permutation."""
    if random.random() <= mutation_chance and len(order) >= 2:
        i, j = random.sample(range(len(order)), 2)
        order[i], order[j] = order[j], order[i]
    return order


def mut_insert(order, mutation_chance):
    """Remove a random element and reinsert at a random position."""
    if random.random() <= mutation_chance and len(order) >= 2:
        i = random.randint(0, len(order) - 1)
        elem = order.pop(i)
        j = random.randint(0, len(order))
        order.insert(j, elem)
    return order


def mut_inversion(order, mutation_chance):
    """Reverse a random subsequence of the permutation."""
    if random.random() <= mutation_chance and len(order) >= 2:
        a, b = sorted(random.sample(range(len(order)), 2))
        order[a : b + 1] = order[a : b + 1][::-1]
    return order


def mut_rk(keys, mutation_chance):
    """Random-keys mutation: perturb one key with Gaussian noise (wrapped).

    Moving one key is the random-keys analogue of a single insert move, so the
    per-gene mutation pressure matches the permutation operators (one move with
    probability mutation_chance per generation).
    """
    if random.random() <= mutation_chance and len(keys) >= 2:
        i = random.randrange(len(keys))
        keys[i] = (keys[i] + random.gauss(0, 0.3)) % 1.0
    return keys


def cx_rk_uniform(ind1, ind2):
    """Uniform crossover on random-keys order genes: swap each key with p=0.5."""
    k1, k2 = ind1[0], ind2[0]
    for i in range(min(len(k1), len(k2))):
        if random.random() < 0.5:
            k1[i], k2[i] = k2[i], k1[i]
    return ind1, ind2


def mutate_multi(ind, num_drones, num_fields, mutation_chance, order_mutation="swap", ablation="full"):
    """Mutate a multi-field individual in-place.

    Mutates field ordering (gene[0]) with the selected operator,
    then independently mutates per-field parameters (genes 1-4).
    """
    MUT_ORDER = {"swap": mut_swap, "insert": mut_insert, "inversion": mut_inversion, "rk": mut_rk}

    # Mutate field ordering
    if ablation != "fixed_order":
        ind[0] = MUT_ORDER[order_mutation](ind[0], mutation_chance)

    def _mutate_drones(drones):
        if not drones:
            drones = [random.randint(0, num_drones - 1)]
        if random.random() < 0.5:
            drones.insert(random.randint(0, len(drones) - 1), random.randint(0, num_drones - 1))
        if random.random() < 0.5 and len(drones) > 1:
            del drones[random.randint(0, len(drones) - 1)]
        if random.random() < 0.5:
            random.shuffle(drones)
        return drones[:MAX_DRONES_ON_CAR]

    # Shared (collapsed) genes are mutated ONCE per generation with the same
    # per-gene chance as an individual field gene, so single_* ablations get
    # the same mutation pressure per gene as the full search — otherwise the
    # shared gene would be mutated up to num_fields times per generation.
    if ablation == "single_direction" and random.random() <= mutation_chance:
        d = (ind[1][0] + random.gauss(0, 45)) % 360
        ind[1] = [d] * num_fields
    if ablation == "single_start" and random.random() <= mutation_chance:
        s = random.choice(["ne", "nw", "se", "sw"])
        ind[2] = [s] * num_fields
    if ablation == "single_drones" and random.random() <= mutation_chance:
        drones = _mutate_drones(ind[3][0][:])
        ind[3] = [drones[:] for _ in range(num_fields)]

    # Mutate per-field parameters
    for field_idx in range(num_fields):
        # Direction
        if ablation not in ("single_direction", "fixed_direction") and random.random() <= mutation_chance:
            ind[1][field_idx] = (ind[1][field_idx] + random.gauss(0, 45)) % 360

        # Start corner
        if ablation not in ("single_start", "fixed_start") and random.random() <= mutation_chance:
            ind[2][field_idx] = random.choice(["ne", "nw", "se", "sw"])

        # Drones
        if ablation not in ("single_drones", "fixed_drones") and random.random() <= mutation_chance:
            ind[3][field_idx] = _mutate_drones(ind[3][field_idx])

        # Car points
        if random.random() <= mutation_chance:
            cps = ind[4][field_idx][:]
            if not cps:
                cps = [random.uniform(0, 1)]
            if random.random() < 0.5:
                cps.insert(random.randint(0, len(cps) - 1), random.uniform(0, 1))
            if random.random() < 0.5 and len(cps) > 1:
                del cps[random.randint(0, len(cps) - 1)]
            if random.random() < 0.75:
                cps = sorted(cps)
            ind[4][field_idx] = cps[:MAX_CAR_POINTS]

    return (ind,)


# --- Evaluation -------------------------------------------------------------


def evaluate_multi_individual(individual, campaign_data, args, pyproj_transformer):
    """Evaluate a multi-field individual.

    Calls get_route() once per field in visit order, sums costs, adds transit.

    Time model: within a field the assigned drones fly concurrently, so the
    field is done when its slowest drone is done (per-field makespan = max over
    drones of cumulative flight time at that field). The truck visits fields
    sequentially, so campaign flight time is the SUM of per-field makespans,
    plus inter-field transit.

    Units: waypoints_distance() returns meters; drone price_per_kilometer is a
    per-km rate, so distance is converted to km for pricing.

    Returns: (distance_m, time_h, drone_price, salary, penalty, starts,
              transit_time_h, grid_total, grid_missed, drone_usage)
    where drone_usage maps drone DB id -> [n_flights, flight_hours].
    """
    from mainapp.service_routing import get_route
    from mainapp.utils import (
        drone_flight_price,
        flight_penalty,
        transit_time_hours,
        waypoints_distance,
        waypoints_flight_time,
    )

    field_order = decode_order(individual[0])
    directions = individual[1]
    starts = individual[2]
    drones_map = individual[3]
    car_points_map = individual[4]

    campaign = campaign_data["campaign"]
    fields_data = campaign_data["fields_data"]
    all_drones = campaign_data["drones_list"]
    truck_speed = getattr(args, "truck_speed", None) or campaign.truck_speed_kmh

    total_distance = 0.0
    total_drone_price = 0.0
    total_starts = 0
    total_transit_time = 0.0
    all_grids_total = 0
    all_grids_traversed = 0
    field_makespans = []
    drones_used = set()
    drone_usage = defaultdict(lambda: [0, 0.0])

    for visit_idx, field_idx in enumerate(field_order):
        fd = fields_data[field_idx]
        drones = [all_drones[i] for i in drones_map[field_idx]]

        # Transit from previous field
        if visit_idx > 0:
            prev_idx = field_order[visit_idx - 1]
            prev_road = fields_data[prev_idx]["road_latlon"]
            this_road = fd["road_latlon"]
            total_transit_time += transit_time_hours(prev_road, this_road, truck_speed)

        # Route this field
        avoidance_config = {
            "strategy": "2d",
            "height_min": 10,
            "height_max": 120,
            "safety_margin": 5,
            "climb_rate": 3,
            "descent_rate": 2,
            "energy_per_meter_climb": 1.5,
            "hole_heights": [0.0] * len(fd["holes"]),
            "strategy_params": None,
        }
        route_kwargs = dict(
            car_move=car_points_map[field_idx],
            direction=directions[field_idx],
            start=starts[field_idx],
            field=[pt[:] for pt in fd["field"]],
            grid_step=campaign.grid_step,
            road=[pt[:] for pt in fd["road"]],
            drones=drones,
            pyproj_transformer=pyproj_transformer,
            avoidance_config=avoidance_config,
        )
        if fd["holes"]:
            route_kwargs["holes"] = [[pt[:] for pt in hole] for hole in fd["holes"]]
            route_kwargs["simple_holes_traversal"] = True

        grid, waypoints, _, _ = get_route(**route_kwargs)

        grid_total = sum(len(line) for line in grid)
        all_grids_total += grid_total

        field_drone_time = defaultdict(float)
        field_covered = set()
        for drone_waypoints in waypoints:
            new_distance = waypoints_distance(drone_waypoints, lat_f=_WP_LAT, lon_f=_WP_LON)
            new_time = waypoints_flight_time(
                drone_waypoints,
                args.max_working_speed,
                lat_f=_WP_LAT,
                lon_f=_WP_LON,
                max_speed_f=_WP_MAX_SPEED,
                slowdown_ratio_f=_WP_SLOWDOWN,
                min_slowdown_ratio_f=_WP_MIN_SLOWDOWN,
                spray_on_f=_WP_SPRAY,
            )
            total_distance += new_distance
            drone_id = drone_waypoints[0]["drone"]["id"]
            field_drone_time[drone_id] += new_time + SETUP_TIME_PER_FLIGHT_HOURS
            drones_used.add(drone_id)
            drone_usage[drone_id][0] += 1
            drone_usage[drone_id][1] += new_time
            total_drone_price += drone_flight_price(drone_waypoints[0]["drone"], new_distance / 1000.0, new_time)
            field_covered.update(
                (round(_WP_LAT(wp), 9), round(_WP_LON(wp), 9)) for wp in drone_waypoints if wp["spray_on"]
            )
            total_starts += 1
        if field_drone_time:
            field_makespans.append(max(field_drone_time.values()))
        all_grids_traversed += len(field_covered)

    if not drones_used:
        return 0, 0, 0, 0, 1_000_000, 0, 0, all_grids_total, all_grids_total, {}

    total_time = sum(field_makespans) + total_transit_time

    # One crew operates the whole campaign regardless of how many drone models
    # fly (drones execute waypoints autonomously; an operator launches one,
    # then services the next). Crew pay is purely per hour + per launch.
    # (The legacy single-field scripts multiplied by the number of drones used;
    # that convention is deliberately NOT carried over here.)
    total_salary = campaign.hourly_price * total_time + campaign.start_price * total_starts

    total_penalty = flight_penalty(
        total_time,
        args.borderline_time,
        args.max_time,
        total_salary,
        total_drone_price,
        all_grids_total,
        all_grids_traversed,
    )

    return (
        total_distance,
        total_time,
        total_drone_price,
        total_salary,
        total_penalty,
        total_starts,
        total_transit_time,
        all_grids_total,
        max(all_grids_total - all_grids_traversed, 0),
        dict(drone_usage),
    )


# --- Toolbox setup ----------------------------------------------------------


def setup_multi_toolbox(
    num_fields, num_drones, evaluate_fn, mutate_fn, crossover_type="ox", ablation="full", order_encoding=None
):
    """Create and configure a DEAP toolbox for multi-field GA."""
    from deap import base, creator, tools
    from scoop import futures

    # Guard against re-creation: DEAP's creator uses module-level classes, and
    # the experiment harness reuses worker processes across many GA runs.
    if not hasattr(creator, "FitnessMax"):
        creator.create("FitnessMax", base.Fitness, weights=TARGET_WEIGHTS)
    if not hasattr(creator, "Individual"):
        creator.create("Individual", list, fitness=creator.FitnessMax)

    if order_encoding is None:
        order_encoding = "rk" if crossover_type == "rk" else "perm"

    toolbox = base.Toolbox()
    toolbox.register(
        "individual",
        tools.initIterate,
        creator.Individual,
        lambda: generate_multi_individual(num_fields, num_drones, ablation, order_encoding),
    )
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("evaluate", evaluate_fn)

    CX_MAP = {"ox": cx_order, "pmx": cx_pmx, "cx": cx_cycle, "rk": cx_rk_uniform}
    ordering_cx = CX_MAP[crossover_type]

    def combined_crossover(ind1, ind2):
        if ablation != "fixed_order":
            ordering_cx(ind1, ind2)
        cx_per_field_params(ind1, ind2, num_fields)
        return ind1, ind2

    toolbox.register("mate", combined_crossover)
    toolbox.register("mutate", mutate_fn)
    toolbox.register("select", tools.selTournament, tournsize=3)
    toolbox.register("map", futures.map)
    return toolbox


# --- GA loop ----------------------------------------------------------------


def run_multi_ga(toolbox, population_size, ngen):
    """Run multi-field GA loop. Returns list of per-generation iteration dicts."""
    from deap import algorithms, tools

    population = toolbox.population(n=population_size)
    iterations = []

    # Evaluate the initial population so it can compete in (mu + lambda)
    # survivor selection below (elitism: parents survive alongside offspring).
    for result, ind in zip(toolbox.map(toolbox.evaluate, population), population):
        ind.fitness.values = (result[2] + result[3] + result[4],)

    for gen in range(ngen):
        print(f"{gen + 1}/{ngen}")
        offspring = algorithms.varAnd(population, toolbox, cxpb=0.5, mutpb=1)
        fits = toolbox.map(toolbox.evaluate, offspring)
        fitness_params = []

        for result, ind in zip(fits, offspring):
            (distance, time, drone_price, salary, penalty, number_of_starts, transit_time) = result[:7]
            ind.fitness.values = (drone_price + salary + penalty,)
            fitness_params.append(
                {
                    "distance": distance,
                    "time": time,
                    "drone_price": drone_price,
                    "salary": salary,
                    "penalty": penalty,
                    "number_of_starts": number_of_starts,
                    "transit_time": transit_time,
                }
            )

        population = toolbox.select(population + offspring, k=len(population))

        best = min(fitness_params, key=lambda x: x["drone_price"] + x["salary"] + x["penalty"])
        n = len(fitness_params)
        best_ind = tools.selBest(population, k=1)[0]
        iterations.append(
            {
                "best_ind": best_ind,
                "best_distance": best["distance"],
                "average_distance": sum(p["distance"] for p in fitness_params) / n,
                "best_time": best["time"],
                "average_time": sum(p["time"] for p in fitness_params) / n,
                "best_drone_price": best["drone_price"],
                "average_drone_price": sum(p["drone_price"] for p in fitness_params) / n,
                "best_salary": best["salary"],
                "average_salary": sum(p["salary"] for p in fitness_params) / n,
                "best_penalty": best["penalty"],
                "average_penalty": sum(p["penalty"] for p in fitness_params) / n,
                "best_number_of_starts": best["number_of_starts"],
                "average_number_of_starts": sum(p["number_of_starts"] for p in fitness_params) / n,
                "best_transit_time": best["transit_time"],
                "average_transit_time": sum(p["transit_time"] for p in fitness_params) / n,
                "best_fit": min(p["drone_price"] + p["salary"] + p["penalty"] for p in fitness_params),
                "average_fit": sum(p["drone_price"] + p["salary"] + p["penalty"] for p in fitness_params) / n,
            }
        )

    return iterations


# --- Result saving ----------------------------------------------------------


def save_multi_results(iterations, args, campaign_data, filename=None):
    """Save Excel report and best individual JSON for multi-field GA."""
    from mainapp.utils_excel import log_excel

    campaign = campaign_data["campaign"]
    fname = filename or args.filename

    field_names = [fd["field_obj"].name for fd in campaign_data["fields_data"]]
    info = {
        "mission": f"Campaign {campaign.id} - {campaign.name}",
        "field": ", ".join(field_names),
        "campaign": f"{campaign.id} - {campaign.name}",
        "fields": ", ".join(field_names),
        "num_fields": campaign_data["num_fields"],
        "population_size": args.population_size,
        "target_weights": TARGET_WEIGHTS,
        "number_of_iterations": args.ngen,
        "grid_step": campaign.grid_step,
        "start_price": campaign.start_price,
        "hourly_price": campaign.hourly_price,
        "truck_speed_kmh": getattr(args, "truck_speed", None) or campaign.truck_speed_kmh,
        "max_working_speed": args.max_working_speed,
        "borderline_time": args.borderline_time,
        "max_time": args.max_time,
        "order_crossover": args.order_crossover,
        "order_mutation": args.order_mutation,
        "ablation": args.ablation,
    }

    log_excel(
        name=fname,
        info=info,
        drones=campaign.drones.all(),
        iterations=iterations,
    )

    try:
        best = iterations[-1]["best_ind"]
        serialized = {
            "field_order": list(best[0]),
            "directions": list(best[1]),
            "starts": list(best[2]),
            "drones": [list(d) for d in best[3]],
            "car_points": [list(c) for c in best[4]],
        }
        with open(f"{fname}.json", "w", encoding="utf-8") as f:
            json.dump({"serialized": serialized}, f, indent=2, ensure_ascii=False)
    except (IndexError, KeyError):
        pass
