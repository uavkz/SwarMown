import json
import random

from deap import creator, base, tools, algorithms
from django.core.management.base import BaseCommand

from mainapp.models import Mission
from routing.default.service import get_route


class Command(BaseCommand):
    def handle(self, *args, **options):
        self.run()

    def run(self):
        number_of_drones = 3
        mission = Mission.objects.get(id=12)
        field = json.loads(mission.field.points_serialized)
        field = [[y, x] for (x, y) in field]
        road = json.loads(mission.field.road_serialized)
        road = [[y, x] for (x, y) in road]

        creator.create("FitnessMax", base.Fitness, weights=(1.0,))
        creator.create("Individual", list, fitness=creator.FitnessMax)

        toolbox = base.Toolbox()

        toolbox.register("attr_direction", random.uniform, 0, 360)
        toolbox.register("attr_start", lambda: ["ne", "nw", "se", "sw"][random.randint(0, 3)])
        toolbox.register("attr_drones", lambda: [random.randint(0, number_of_drones-1) for _ in range(random.randint(1, number_of_drones*3))])
        toolbox.register("attr_car_points", lambda: [random.uniform(0, 1) for _ in range(random.randint(1, number_of_drones*2))])

        toolbox.register("individual", tools.initCycle, creator.Individual,
                         (toolbox.attr_direction, toolbox.attr_start, toolbox.attr_drones, toolbox.attr_car_points
                          ))

        toolbox.register("population", tools.initRepeat, list, toolbox.individual)

        def eval(individual):
            drones = [list(mission.drones.all())[i] for i in individual[2]]
            route = get_route(car_move=individual[3], direction=individual[0], target=None, height_diff=None, round_start_zone=None,
                              start=individual[1], field=field, grid_step=mission.grid_step, feature3=None, feature4=None, road=road, drones=drones)
            return 0,

        toolbox.register("evaluate", eval)
        toolbox.register("mate", tools.cxTwoPoint)
        toolbox.register("mutate", lambda x: (x, ))
        toolbox.register("select", tools.selTournament, tournsize=3)

        population = toolbox.population(n=5)

        NGEN = 5
        for gen in range(NGEN):
            print(gen)
            offspring = algorithms.varAnd(population, toolbox, cxpb=0.5, mutpb=0.1)
            fits = toolbox.map(toolbox.evaluate, offspring)
            for fit, ind in zip(fits, offspring):
                ind.fitness.values = fit
            population = toolbox.select(offspring, k=len(population))
        top10 = tools.selBest(population, k=10)
        print(top10)
