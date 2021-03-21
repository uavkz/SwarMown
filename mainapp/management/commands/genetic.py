try:
    import os
    import sys

    from django.conf import settings

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
    import django
    django.setup()
except Exception as e:
    pass

import json
import random

from deap import creator, base, tools, algorithms
from django.core.management.base import BaseCommand
from scoop import futures

from mainapp.models import Mission
from mainapp.utils import waypoints_distance, waypoints_flight_time, drone_flight_price
from mainapp.utils_excel import log_excel
from routing.default.service import get_route


def eval(individual):
    drones = [list(mission.drones.all().order_by('id'))[i] for i in individual[2]]
    grid, waypoints, _, initial = get_route(car_move=individual[3], direction=individual[0], target=None, height_diff=None, round_start_zone=None,
                      start=individual[1], field=field, grid_step=mission.grid_step, feature3=None, feature4=None, road=road, drones=drones)
    distance = 0
    time = 0
    price = 0

    for drone_waypoints in waypoints:
        new_distance = waypoints_distance(drone_waypoints, lat_f=lambda x: x['lat'], lon_f=lambda x: x['lon'])
        new_time = waypoints_flight_time(drone_waypoints, lat_f=lambda x: x['lat'],
                                         lon_f=lambda x: x['lon'],
                                         max_speed_f=lambda x: x['drone']['max_speed'],
                                         slowdown_ratio_f=lambda x: x['drone']['slowdown_ratio_per_degree'],
                                         min_slowdown_ratio_f=lambda x: x['drone']['min_slowdown_ratio'])
        distance += new_distance
        time += new_time
        price += drone_flight_price(drone_waypoints[0]['drone'], new_distance, new_time)
    number_of_starts = len(waypoints)
    return distance, time, price, number_of_starts


MISSION_ID = 12
NGEN = 10
POPULATION_SIZE = 16
# Distance, Time, Price, NumberOfStarts
TARGET_WEIGHTS = (-1.0, -1.0, -1.0, -1.0)

mission = Mission.objects.get(id=MISSION_ID)
field = json.loads(mission.field.points_serialized)
field = [[y, x] for (x, y) in field]
road = json.loads(mission.field.road_serialized)
road = [[y, x] for (x, y) in road]
number_of_drones = mission.drones.all().count()

toolbox = base.Toolbox()

creator.create("FitnessMax", base.Fitness, weights=TARGET_WEIGHTS)
creator.create("Individual", list, fitness=creator.FitnessMax)

toolbox.register("attr_direction", random.uniform, 0, 360) # 0
toolbox.register("attr_start", lambda: ["ne", "nw", "se", "sw"][random.randint(0, 3)]) # 1
toolbox.register("attr_drones", lambda: [random.randint(0, number_of_drones - 1) for _ in
                                         range(random.randint(1, number_of_drones * 3))]) # 2
toolbox.register("attr_car_points",
                 lambda: [random.uniform(0, 1) for _ in range(random.randint(1, number_of_drones * 2))]) # 3

toolbox.register("individual", tools.initCycle, creator.Individual,
                 (toolbox.attr_direction, toolbox.attr_start, toolbox.attr_drones, toolbox.attr_car_points
                  ))

toolbox.register("population", tools.initRepeat, list, toolbox.individual)

toolbox.register("evaluate", eval)
toolbox.register("mate", tools.cxTwoPoint)
toolbox.register("mutate", lambda x: (x,))
toolbox.register("select", tools.selTournament, tournsize=3)
toolbox.register("map", futures.map)


class Command(BaseCommand):
    def handle(self, *args, **options):
        self.run()

    def run(self):
        global toolbox
        population = toolbox.population(n=POPULATION_SIZE)

        iterations = []
        for gen in range(NGEN):
            print(f"{gen}/{NGEN}")
            offspring = algorithms.varAnd(population, toolbox, cxpb=0.5, mutpb=0.1)
            fits = toolbox.map(toolbox.evaluate, offspring)
            for fit, ind in zip(fits, offspring):
                ind.fitness.values = fit
            population = toolbox.select(offspring, k=len(population))
            top = tools.selBest(population, k=1)

            fitnesses = [sum([t * tw for t, tw in zip(ind.fitness.values, TARGET_WEIGHTS)]) for ind in offspring]
            iterations.append(
                {
                    "best_ind": top[0],

                    "best_distance": min((ind.fitness.values[0] for ind in offspring)),
                    "average_distance": sum((ind.fitness.values[0] for ind in offspring)) / len(offspring),
                    "best_time": min((ind.fitness.values[1] for ind in offspring)),
                    "average_time": sum((ind.fitness.values[1] for ind in offspring)) / len(offspring),
                    "best_price": min((ind.fitness.values[2] for ind in offspring)),
                    "average_price": sum((ind.fitness.values[2] for ind in offspring)) / len(offspring),
                    "best_number_of_starts": min((ind.fitness.values[3] for ind in offspring)),
                    "average_number_of_starts": sum((ind.fitness.values[3] for ind in offspring)) / len(offspring),

                    "best_fit": max(fitnesses),
                    "average_fit": sum(fitnesses) / len(fitnesses)
                }
            )

        log_excel(
            name="test",
            info={
                "population_size": POPULATION_SIZE,
                "target_weights": TARGET_WEIGHTS,
                "number_of_iterations": NGEN,
                "mission": f"{mission.id} - {mission.name}",
                "field": f"{mission.field.id} - {mission.field.name}",
                "grid_step": mission.grid_step
            },
            drones=mission.drones.all(),
            iterations=iterations,
        )
