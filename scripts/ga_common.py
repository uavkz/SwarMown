"""Shared logic for genetic algorithm scripts.

Contains: Django bootstrap, argument parsing, mission loading, individual
evaluation, mutation, DEAP toolbox setup, and the main GA loop.
"""

import json
import random
from collections import defaultdict
from pathlib import Path

from mainapp.service_routing import get_route
from mainapp.utils import (
    drone_flight_price,
    flight_penalty,
    waypoints_distance,
    waypoints_flight_time,
    waypoints_total_climb,
)
from mainapp.utils_excel import log_excel

# --- Django bootstrap -------------------------------------------------------

SETUP_TIME_PER_FLIGHT_HOURS = 15 / 60
MAX_DRONES_ON_CAR = 5
TARGET_WEIGHTS = (-1.0,)

# Lambda accessors for dict-based waypoints (used by GA eval, not Django ORM)
_WP_LAT = lambda x: x["lat"]  # noqa: E731
_WP_LON = lambda x: x["lon"]  # noqa: E731
_WP_MAX_SPEED = lambda x: x["drone"]["max_speed"]  # noqa: E731
_WP_SLOWDOWN = lambda x: x["drone"]["slowdown_ratio_per_degree"]  # noqa: E731
_WP_MIN_SLOWDOWN = lambda x: x["drone"]["min_slowdown_ratio"]  # noqa: E731
_WP_SPRAY = lambda x: x["spray_on"]  # noqa: E731
_WP_HEIGHT = lambda x: x["height"]  # noqa: E731


def bootstrap_django():
    """Set up Django environment for script usage."""
    import os
    import sys

    project_root = str(Path(__file__).resolve().parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
    import django

    django.setup()


def build_argparser():
    """Create the standard argument parser for GA scripts."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mission_id", "-m", type=int, required=True)
    parser.add_argument("--ngen", "-n", type=int, required=True)
    parser.add_argument("--population_size", "-p", type=int, required=True)
    parser.add_argument("--filename", "-f", required=True, help="Output filename (no extension)")
    parser.add_argument("--max-time", "-t", type=float, required=True)
    parser.add_argument("--borderline_time", "-b", type=float, required=True)
    parser.add_argument("--max_working_speed", "-mxs", type=float, required=True)
    parser.add_argument("--mutation_chance", "-mt", type=float, required=True)
    # 3D obstacle avoidance parameters
    parser.add_argument("--height_min", type=float, default=10.0, help="Working flight altitude AGL (meters)")
    parser.add_argument("--height_max", type=float, default=120.0, help="Max allowed flight altitude AGL (meters)")
    parser.add_argument("--safety_margin", type=float, default=5.0, help="Safety margin above obstacle top (meters)")
    parser.add_argument(
        "--obstacle_heights", type=str, default=None, help='JSON list of obstacle heights in meters, e.g. "[15, 20]"'
    )
    parser.add_argument("--climb_rate", type=float, default=3.0, help="Max climb rate (m/s)")
    parser.add_argument("--descent_rate", type=float, default=2.0, help="Max descent rate (m/s)")
    parser.add_argument(
        "--energy_per_meter_climb", type=float, default=1.5, help="Climb energy cost multiplier vs horizontal"
    )
    parser.add_argument(
        "--avoidance_strategy",
        type=str,
        default="2d",
        choices=["2d", "greedy", "B1", "B2", "B3", "B4", "B5", "B6", "B1s", "B2s", "B3s", "B4s", "B5s", "B6s"],
        help="Obstacle avoidance strategy (2d=always around, greedy=per-crossing, B*=GA-optimized, *s=single)",
    )
    return parser


def load_mission(mission_id):
    """Load mission, field, road, holes, and drones from DB. Returns a dict."""
    from mainapp.models import Mission

    mission = Mission.objects.get(id=mission_id)
    field = [[y, x] for x, y in json.loads(mission.field.points_serialized)]
    road = [[y, x] for x, y in json.loads(mission.field.road_serialized)]
    drones_list = list(mission.drones.all().order_by("id"))

    # Parse holes (swap lat/lon to lon/lat like field/road)
    holes_raw = json.loads(mission.field.holes_serialized)
    holes = [[[y, x] for x, y in hole] for hole in holes_raw if len(hole) >= 3]

    return {
        "mission": mission,
        "field": field,
        "road": road,
        "holes": holes,
        "drones_list": drones_list,
        "num_drones": len(drones_list),
    }


def parse_obstacle_heights(args, num_holes):
    """Parse obstacle heights from CLI args. Returns list of heights in meters.

    If --obstacle_heights is provided, uses those values.
    Otherwise returns all zeros (2D behavior — obstacles have no height).
    """
    if args.obstacle_heights:
        heights = json.loads(args.obstacle_heights)
        if len(heights) != num_holes:
            raise ValueError(f"--obstacle_heights has {len(heights)} values but mission has {num_holes} holes")
        return [float(h) for h in heights]
    return [0.0] * num_holes


def build_avoidance_config(args, hole_heights):
    """Build the avoidance configuration dict from CLI args and hole heights."""
    return {
        "hole_heights": hole_heights,
        "height_min": args.height_min,
        "height_max": args.height_max,
        "safety_margin": args.safety_margin,
        "climb_rate": args.climb_rate,
        "descent_rate": args.descent_rate,
        "energy_per_meter_climb": args.energy_per_meter_climb,
        "strategy": args.avoidance_strategy,
        "strategy_params": None,  # set by GA for B* strategies
    }


def make_pyproj_transformer():
    from pyproj import Transformer

    return Transformer.from_crs("epsg:4087", "epsg:4326", always_xy=True)


# --- Evaluation -------------------------------------------------------------


def evaluate_individual(
    individual,
    mission_data,
    args,
    pyproj_transformer,
    triangulation_requirements=None,
    simple_holes_traversal=False,
    avoidance_config=None,
):
    """Evaluate a single GA individual. Returns (distance, time, drone_price,
    salary, penalty, number_of_starts)."""
    mission = mission_data["mission"]
    drones = [mission_data["drones_list"][i] for i in individual[2]]
    holes = mission_data.get("holes", [])

    route_kwargs = dict(
        car_move=individual[3],
        direction=individual[0],
        start=individual[1],
        field=mission_data["field"],
        grid_step=mission.grid_step,
        road=mission_data["road"],
        drones=drones,
        pyproj_transformer=pyproj_transformer,
    )
    if holes:
        route_kwargs["holes"] = holes
    if triangulation_requirements is not None:
        route_kwargs["triangulation_requirements"] = triangulation_requirements
    if simple_holes_traversal:
        route_kwargs["simple_holes_traversal"] = True

    # 3D avoidance: inject strategy_params from gene[4] if present
    if avoidance_config is not None:
        ac = dict(avoidance_config)
        if len(individual) > 4:
            ac["strategy_params"] = individual[4]
        route_kwargs["avoidance_config"] = ac

    grid, waypoints, _, _ = get_route(**route_kwargs)

    use_3d = avoidance_config is not None and avoidance_config.get("strategy", "2d") != "2d"

    distance = 0
    drone_price, salary, penalty = 0, 0, 0
    number_of_starts = len(waypoints)
    grid_traversed = 0
    grid_total = sum(len(line) for line in grid)

    drone_flight_time = defaultdict(int)
    for drone_waypoints in waypoints:
        new_distance = waypoints_distance(drone_waypoints, lat_f=_WP_LAT, lon_f=_WP_LON)
        flight_time_kwargs = dict(
            lat_f=_WP_LAT,
            lon_f=_WP_LON,
            max_speed_f=_WP_MAX_SPEED,
            slowdown_ratio_f=_WP_SLOWDOWN,
            min_slowdown_ratio_f=_WP_MIN_SLOWDOWN,
            spray_on_f=_WP_SPRAY,
        )
        if use_3d:
            flight_time_kwargs["height_f"] = _WP_HEIGHT
            flight_time_kwargs["climb_rate"] = avoidance_config["climb_rate"]
            flight_time_kwargs["descent_rate"] = avoidance_config["descent_rate"]
        new_time = waypoints_flight_time(drone_waypoints, args.max_working_speed, **flight_time_kwargs)
        distance += new_distance
        drone_flight_time[drone_waypoints[0]["drone"]["id"]] += new_time + SETUP_TIME_PER_FLIGHT_HOURS

        climb_meters = 0
        energy_per_meter = 0
        if use_3d:
            climb_meters = waypoints_total_climb(drone_waypoints, height_f=_WP_HEIGHT)
            energy_per_meter = avoidance_config["energy_per_meter_climb"]
        drone_price += drone_flight_price(
            drone_waypoints[0]["drone"], new_distance, new_time, climb_meters, energy_per_meter
        )
        grid_traversed += max(0, len(drone_waypoints) - 2)

    if not drone_flight_time:
        return 0, 0, 0, 0, 1_000_000, 0

    time = max(drone_flight_time.values())
    salary = mission.hourly_price * time * len(drone_flight_time) + mission.start_price * number_of_starts
    penalty = flight_penalty(time, args.borderline_time, args.max_time, salary, drone_price, grid_total, grid_traversed)
    return distance, time, drone_price, salary, penalty, number_of_starts


# --- Mutation ---------------------------------------------------------------


def generate_avoidance_gene(strategy, num_holes):
    """Generate a random gene[4] for the given avoidance strategy."""
    is_single = strategy.endswith("s")
    base = strategy.rstrip("s")
    n = 1 if is_single else max(num_holes, 1)

    if base == "B1":
        return [random.randint(0, 1) for _ in range(n)]
    elif base == "B2":
        return [random.uniform(0, 50) for _ in range(n)]
    elif base == "B3":
        return [random.uniform(0, 500) for _ in range(n)]
    elif base == "B4":
        return [(random.uniform(0, 360), random.uniform(0, 360)) for _ in range(n)]
    elif base == "B5":
        return [(random.uniform(0, 50), random.uniform(0, 500)) for _ in range(n)]
    elif base == "B6":
        return [(random.uniform(0, 360), random.uniform(0, 360), random.uniform(0, 50)) for _ in range(n)]
    return None


def mutate_avoidance_gene(gene, strategy, mutation_chance):
    """Mutate gene[4] in-place for the given avoidance strategy."""
    if gene is None:
        return gene
    base = strategy.rstrip("s")
    for i in range(len(gene)):
        if random.random() > mutation_chance:
            continue
        if base == "B1":
            gene[i] = 1 - gene[i]  # flip bit
        elif base == "B2":
            gene[i] = max(0, gene[i] + random.gauss(0, 10))
        elif base == "B3":
            gene[i] = max(0, gene[i] + random.gauss(0, 50))
        elif base == "B4":
            a, b = gene[i]
            gene[i] = ((a + random.gauss(0, 30)) % 360, (b + random.gauss(0, 30)) % 360)
        elif base == "B5":
            mc, wt = gene[i]
            gene[i] = (max(0, mc + random.gauss(0, 10)), max(0, wt + random.gauss(0, 50)))
        elif base == "B6":
            a, b, mc = gene[i]
            gene[i] = (
                (a + random.gauss(0, 30)) % 360,
                (b + random.gauss(0, 30)) % 360,
                max(0, mc + random.gauss(0, 10)),
            )
    return gene


def custom_mutate(ind, num_drones, mutation_chance, avoidance_strategy=None):
    """Mutate an individual in-place. Returns (ind,) per DEAP convention."""
    direction = ind[0]
    start = ind[1]
    drones = ind[2]
    car_points = ind[3]

    if not car_points:
        car_points = [random.uniform(0, 1)]
    if not drones:
        drones = [random.randint(0, num_drones - 1)]

    if random.random() <= mutation_chance:
        direction += random.gauss(0, 45)
        direction %= 360

    if random.random() <= mutation_chance:
        start = random.choice(["ne", "nw", "se", "sw"])

    if random.random() <= mutation_chance:
        if random.random() < 0.5:
            drones.insert(random.randint(0, len(drones) - 1), random.randint(0, num_drones - 1))
        if random.random() < 0.5 and len(drones) > 1:
            del drones[random.randint(0, len(drones) - 1)]
        if random.random() < 0.5:
            random.shuffle(drones)

    if random.random() <= mutation_chance:
        if random.random() < 0.5:
            car_points.insert(random.randint(0, len(car_points) - 1), random.uniform(0, 1))
        if random.random() < 0.5 and len(car_points) > 1:
            del car_points[random.randint(0, len(car_points) - 1)]
        if random.random() < 0.75:
            car_points = sorted(car_points)

    if not car_points:
        car_points = [random.uniform(0, 1)]
    if not drones:
        drones = [random.randint(0, num_drones - 1)]

    drones = drones[:MAX_DRONES_ON_CAR]
    ind[0] = direction
    ind[1] = start
    ind[2] = drones
    ind[3] = car_points

    # Mutate gene[4] (avoidance params) if present
    if len(ind) > 4 and avoidance_strategy:
        ind[4] = mutate_avoidance_gene(ind[4], avoidance_strategy, mutation_chance)

    return (ind,)


# --- DEAP Toolbox -----------------------------------------------------------


def setup_toolbox(num_drones, evaluate_fn, mutate_fn, avoidance_strategy=None, num_holes=0):
    """Create and configure a DEAP toolbox.

    When avoidance_strategy is a B* strategy, individuals get a 5th gene
    for obstacle avoidance parameters.
    """
    from deap import base, creator, tools
    from scoop import futures

    creator.create("FitnessMax", base.Fitness, weights=TARGET_WEIGHTS)
    creator.create("Individual", list, fitness=creator.FitnessMax)

    toolbox = base.Toolbox()
    toolbox.register("attr_direction", random.uniform, 0, 360)
    toolbox.register("attr_start", lambda: random.choice(["ne", "nw", "se", "sw"]))
    toolbox.register(
        "attr_drones",
        lambda: [random.randint(0, num_drones - 1) for _ in range(random.randint(1, num_drones * 3))],
    )
    toolbox.register("attr_car_points", lambda: [random.uniform(0, 1) for _ in range(random.randint(1, 5))])

    gene_generators = (toolbox.attr_direction, toolbox.attr_start, toolbox.attr_drones, toolbox.attr_car_points)

    # Add gene[4] for GA avoidance strategies
    uses_ga_gene = avoidance_strategy and avoidance_strategy not in ("2d", "greedy")
    if uses_ga_gene:
        toolbox.register("attr_avoidance", generate_avoidance_gene, avoidance_strategy, num_holes)
        gene_generators = (*gene_generators, toolbox.attr_avoidance)

    toolbox.register(
        "individual",
        tools.initCycle,
        creator.Individual,
        gene_generators,
    )
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("evaluate", evaluate_fn)
    toolbox.register("mate", tools.cxTwoPoint)
    toolbox.register("mutate", mutate_fn)
    toolbox.register("select", tools.selTournament, tournsize=3)
    toolbox.register("map", futures.map)
    return toolbox


# --- GA Loop ----------------------------------------------------------------


def run_ga(toolbox, population_size, ngen, target_weights=TARGET_WEIGHTS):
    """Run the main GA loop. Returns list of per-generation iteration dicts."""
    from deap import algorithms, tools

    population = toolbox.population(n=population_size)
    iterations = []

    for gen in range(ngen):
        print(f"{gen + 1}/{ngen}")
        offspring = algorithms.varAnd(population, toolbox, cxpb=0.5, mutpb=1)
        fits = toolbox.map(toolbox.evaluate, offspring)
        fitness_params = []

        for (distance, time, drone_price, salary, penalty, number_of_starts), ind in zip(fits, offspring):
            ind[2] = ind[2][:number_of_starts]
            ind[3] = ind[3][:number_of_starts]
            ind.fitness.values = (drone_price + salary + penalty,)
            fitness_params.append(
                {
                    "distance": distance,
                    "time": time,
                    "drone_price": drone_price,
                    "salary": salary,
                    "penalty": penalty,
                    "number_of_starts": number_of_starts,
                }
            )

        population = toolbox.select(offspring, k=len(population))
        top = tools.selBest(population, k=1)

        fitnesses = [sum(t * tw for t, tw in zip(ind.fitness.values, target_weights)) for ind in offspring]
        best = min(fitness_params, key=lambda x: x["drone_price"] + x["salary"] + x["penalty"])
        n = len(fitness_params)
        iterations.append(
            {
                "best_ind": top[0],
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
                "best_fit": max(fitnesses),
                "average_fit": sum(fitnesses) / len(fitnesses),
            }
        )
        print(f"Top score {max(fitnesses)}, average score {sum(fitnesses) / len(fitnesses)}")

    return iterations


def save_results(iterations, args, mission, filename=None, extra_info=None, **excel_kwargs):
    """Save Excel report and best individual JSON."""
    fname = filename or args.filename
    info = {
        "population_size": args.population_size,
        "target_weights": TARGET_WEIGHTS,
        "number_of_iterations": args.ngen,
        "mission": f"{mission.id} - {mission.name}",
        "field": f"{mission.field.id} - {mission.field.name}",
        "grid_step": mission.grid_step,
        "start_price": mission.start_price,
        "hourly_price": mission.hourly_price,
        "max_working_speed": args.max_working_speed,
        "borderline_time": args.borderline_time,
        "max_time": args.max_time,
        "avoidance_strategy": args.avoidance_strategy,
        "height_min": args.height_min,
        "height_max": args.height_max,
        "safety_margin": args.safety_margin,
        "climb_rate": args.climb_rate,
        "descent_rate": args.descent_rate,
        "energy_per_meter_climb": args.energy_per_meter_climb,
    }
    if extra_info:
        info.update(extra_info)

    log_excel(
        name=fname,
        info=info,
        drones=mission.drones.all(),
        iterations=iterations,
        **excel_kwargs,
    )

    try:
        best = iterations[-1]["best_ind"]
        serialized = [best[0], best[1], list(best[2]), list(best[3])]
        if len(best) > 4:
            serialized.append(_serialize_avoidance_gene(best[4]))
        with open(f"{fname}.json", "w", encoding="utf-8") as f:
            json.dump({"serialized": serialized}, f)
    except Exception:
        pass


def _serialize_avoidance_gene(gene):
    """Convert avoidance gene[4] to JSON-serializable format."""
    result = []
    for item in gene:
        if isinstance(item, (list, tuple)):
            result.append(list(item))
        else:
            result.append(item)
    return result
