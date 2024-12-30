from concurrent.futures import ThreadPoolExecutor

from pyproj import Transformer

try:
    import os, sys
    sys.path.append('C:\\Архив\\Наука-старое\\UAV-Related\\SwarMown')
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")

    import django
    django.setup()
except Exception as e:
    pass

import json
import random
from collections import defaultdict

import argparse
from deap import creator, base, tools, algorithms
from scoop import futures

from mainapp.models import Mission
from mainapp.utils import waypoints_distance, waypoints_flight_time, drone_flight_price, flight_penalty
from mainapp.utils_excel import log_excel
from mainapp.service_routing import get_route

parser = argparse.ArgumentParser()

# Add long and short argument
parser.add_argument("--mission_id", "-m", help="Mission id")
parser.add_argument("--ngen", "-n", help="Number of generations")
parser.add_argument("--population_size", "-p", help="Population size")
parser.add_argument("--filename", "-f", help="Filename for output (without extension)")
parser.add_argument("--max-time", "-t", help="Maximum time")
parser.add_argument("--borderline_time", "-b", help="Borderline time")
parser.add_argument("--max_working_speed", "-mxs", help="Max working speed")
parser.add_argument("--mutation_chance", "-mt", help="Mutation chance")

# Read arguments from the command line
args = parser.parse_args()


def eval_core(individual, triangulation_requirements):
    drones = [list(mission.drones.all().order_by('id'))[i] for i in individual[2]]
    grid, waypoints, _, initial = get_route(
        car_move=individual[3],
        direction=individual[0],
        start=individual[1],
        field=field,
        grid_step=mission.grid_step,
        road=road,
        drones=drones,
        pyproj_transformer=pyproj_transformer,
        triangulation_requirements=triangulation_requirements
    )
    distance = 0
    drone_price, salary, penalty = 0, 0, 0
    number_of_starts = len(waypoints)
    grid_traversed = 0
    grid_total = sum([len(line) for line in grid])

    drone_flight_time = defaultdict(int)
    for drone_waypoints in waypoints:
        new_distance = waypoints_distance(
            drone_waypoints, lat_f=lambda x: x['lat'], lon_f=lambda x: x['lon']
        )
        new_time = waypoints_flight_time(
            drone_waypoints,
            float(args.max_working_speed),
            lat_f=lambda x: x['lat'],
            lon_f=lambda x: x['lon'],
            max_speed_f=lambda x: x['drone']['max_speed'],
            slowdown_ratio_f=lambda x: x['drone']['slowdown_ratio_per_degree'],
            min_slowdown_ratio_f=lambda x: x['drone']['min_slowdown_ratio'],
            spray_on_f=lambda x: x['spray_on']
        )
        distance += new_distance
        drone_flight_time[drone_waypoints[0]['drone']['id']] += new_time + (15 / 60)
        drone_price_n = drone_flight_price(drone_waypoints[0]['drone'], new_distance, new_time)
        drone_price += drone_price_n
        grid_traversed += max(0, len(drone_waypoints) - 2)

    time = max(drone_flight_time.values())
    salary = mission.hourly_price * time * len(drone_flight_time) + mission.start_price * number_of_starts
    penalty = flight_penalty(time, float(args.borderline_time), float(args.max_time), salary, drone_price, grid_total, grid_traversed)
    return distance, time, drone_price, salary, penalty, number_of_starts


def eval(individual):
    return eval_core(individual, BEST_REQS)

def custom_mutate(ind):
    direction = ind[0]
    start = ind[1]
    drones = ind[2]
    car_points = ind[3]

    if not car_points:
        car_points = [random.uniform(0, 1)]

    if not drones:
        drones = [random.randint(0, number_of_drones - 1)]

    if random.random() <= MUTATION_CHANCE:
        direction += random.gauss(0, 45)
        direction %= 360

    if random.random() <= MUTATION_CHANCE:
        start = ["ne", "nw", "se", "sw"][random.randint(0, 3)]

    if random.random() <= MUTATION_CHANCE:
        if random.random() < 0.5: # Insert random
            drones.insert(random.randint(0, len(drones) - 1), random.randint(0, number_of_drones - 1))

        if random.random() < 0.5 and len(drones) > 1: # Delete random
            del drones[random.randint(0, len(drones) - 1)]

        if random.random() < 0.5: # Shuffle random
            random.shuffle(drones)

    if random.random() <= MUTATION_CHANCE:
        if random.random() < 0.5:  # Insert random
            car_points.insert(random.randint(0, len(car_points) - 1), random.uniform(0, 1))

        if random.random() < 0.5 and len(car_points) > 1:  # Delete random
            del car_points[random.randint(0, len(car_points) - 1)]

        if random.random() < 0.75:  # Sort
            car_points = list(sorted(car_points))

    if not car_points:
        car_points = [random.uniform(0, 1)]

    if not drones:
        drones = [random.randint(0, number_of_drones - 1)]

    drones = drones[:MAX_DRONES_ON_CAR]
    ind[0] = direction
    ind[1] = start
    ind[2] = drones
    ind[3] = car_points
    return ind,


# Best requirements for the triangulation of the field with holes
BEST_REQS = None

MISSION_ID = int(args.mission_id)
NGEN = int(args.ngen)
POPULATION_SIZE = int(args.population_size)
MUTATION_CHANCE = float(args.mutation_chance)
# Distance, Time, Price, NumberOfStarts
TARGET_WEIGHTS = (-1.0, )

MAX_DRONES_ON_CAR = 5

mission = Mission.objects.get(id=MISSION_ID)
field = json.loads(mission.field.points_serialized)
field = [[y, x] for (x, y) in field]
road = json.loads(mission.field.road_serialized)
road = [[y, x] for (x, y) in road]
number_of_drones = mission.drones.all().count()

pyproj_transformer = Transformer.from_crs(
    'epsg:4087',
    'epsg:4326',
    always_xy=True,
)

toolbox = base.Toolbox()

creator.create("FitnessMax", base.Fitness, weights=TARGET_WEIGHTS)
creator.create("Individual", list, fitness=creator.FitnessMax)

toolbox.register("attr_direction", random.uniform, 0, 360) # 0
toolbox.register("attr_start", lambda: ["ne", "nw", "se", "sw"][random.randint(0, 3)]) # 1
toolbox.register("attr_drones", lambda: [random.randint(0, number_of_drones - 1) for _ in
                                         range(random.randint(1, number_of_drones * 3))]) # 2
toolbox.register("attr_car_points",
                 lambda: [random.uniform(0, 1) for _ in range(random.randint(1, 5))]) # 3

toolbox.register("individual", tools.initCycle, creator.Individual,
                 (toolbox.attr_direction, toolbox.attr_start, toolbox.attr_drones, toolbox.attr_car_points)
                 )

toolbox.register("population", tools.initRepeat, list, toolbox.individual)

toolbox.register("evaluate", eval)
toolbox.register("mate", tools.cxTwoPoint)
toolbox.register("mutate", custom_mutate)
toolbox.register("select", tools.selTournament, tournsize=3)
toolbox.register("map", futures.map)


def run():
    global BEST_REQS
    NUM_RANDOM_INDIVS = 7
    NUM_RANDOM_REQUIREMENTS = 15

    def generate_random_requirements_sets(n):
        from pode import Requirement

        sets_ = []
        for _ in range(n):
            total = 1.0
            count = random.randint(1, 5)
            vals = []
            for _ in range(count - 1):
                val = random.uniform(0, total)
                total -= val
                vals.append(val)
            vals.append(total)
            random.shuffle(vals)
            sets_.append([Requirement(v) for v in vals])
        return sets_

    def generate_random_individual():
        direction = random.uniform(0, 360)
        start = ["ne", "nw", "se", "sw"][random.randint(0, 3)]
        drones_ = [random.randint(0, number_of_drones - 1) for _ in range(random.randint(1, number_of_drones * 3))]
        car_points_ = [random.uniform(0, 1) for _ in range(random.randint(1, 5))]
        return [direction, start, drones_, car_points_]

    req_sets = generate_random_requirements_sets(NUM_RANDOM_REQUIREMENTS)
    random_inds = [generate_random_individual() for _ in range(NUM_RANDOM_INDIVS)]

    combos = []
    for ind in random_inds:
        for req in req_sets:
            combos.append((ind, req))

    def pre_eval_worker(arg):
        indiv, reqs = arg
        dist, tm, dprice, sal, pen, starts = eval_core(indiv, reqs)
        return {
            "dist": dist,
            "time": tm,
            "drone_price": dprice,
            "salary": sal,
            "penalty": pen,
            "starts": starts,
            "req": reqs,
            "ind": indiv
        }

    print("Getting best requirements set")
    with ThreadPoolExecutor(max_workers=8) as executor: # TODO change max_workers
        results = list(executor.map(pre_eval_worker, combos))

    best_preeval = min(results, key=lambda x: x["drone_price"] + x["salary"] + x["penalty"])
    BEST_REQS = best_preeval["req"]
    print("Best requirements set found")

    global toolbox
    population = toolbox.population(n=POPULATION_SIZE)

    iterations = []
    for gen in range(NGEN):
        print(f"{gen+1}/{NGEN}")
        offspring = algorithms.varAnd(population, toolbox, cxpb=0.5, mutpb=1)
        fits = toolbox.map(toolbox.evaluate, offspring)
        fitness_params = []
        for (distance, time, drone_price, salary, penalty, number_of_starts), ind in zip(fits, offspring):
            ind.fitness.values = (drone_price + salary + penalty, )
            ind[2] = ind[2][:number_of_starts]
            ind[3] = ind[3][:number_of_starts]
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

        fitnesses = [sum([t * tw for t, tw in zip(ind.fitness.values, TARGET_WEIGHTS)]) for ind in offspring]
        best_solution = min(fitness_params, key=lambda x: x['drone_price'] + x['salary'] + x['penalty'])
        iterations.append(
            {
                "best_ind": top[0],

                "best_distance": best_solution['distance'],
                "average_distance": sum((ind['distance'] for ind in fitness_params)) / len(fitness_params),
                "best_time": best_solution['time'],
                "average_time": sum((ind['time'] for ind in fitness_params)) / len(fitness_params),
                "best_drone_price": best_solution['drone_price'],
                "average_drone_price": sum((ind['drone_price'] for ind in fitness_params)) / len(fitness_params),
                "best_salary": best_solution['salary'],
                "average_salary": sum((ind['salary'] for ind in fitness_params)) / len(fitness_params),
                "best_penalty": best_solution['penalty'],
                "average_penalty": sum((ind['penalty'] for ind in fitness_params)) / len(fitness_params),
                "best_number_of_starts": best_solution['number_of_starts'],
                "average_number_of_starts": sum((ind['number_of_starts'] for ind in fitness_params)) / len(fitness_params),

                "best_fit": max(fitnesses),
                "average_fit": sum(fitnesses) / len(fitnesses)
            }
        )
        print(f"Top score {max(fitnesses)}, average score {sum(fitnesses) / len(fitnesses)}")

    log_excel(
        name=args.filename,
        info={
            "population_size": POPULATION_SIZE,
            "target_weights": TARGET_WEIGHTS,
            "number_of_iterations": NGEN,
            "mission": f"{mission.id} - {mission.name}",
            "field": f"{mission.field.id} - {mission.field.name}",
            "grid_step": mission.grid_step,
            "start_price": mission.start_price,
            "hourly_price": mission.hourly_price,
            "max_working_speed": float(args.max_working_speed),
            "borderline_time": float(args.borderline_time),
            "max_time": float(args.max_time),
        },
        drones=mission.drones.all(),
        iterations=iterations,
        best_reqs=BEST_REQS,
    )


if __name__ == "__main__":
    run()
