import xlwt

try:
    import os
    import sys

    from django.conf import settings

    # sys.path.append('C:\\Users\\KindYAK\\Desktop\\SwarMown\\')
    sys.path.append('/home/a.bekbaganbetov/SwarMown')
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
    import django
    django.setup()
except Exception as e:
    pass

import json
import random

from mainapp.models import *
from mainapp.utils import drone_flight_price, flight_penalty
from routing.default.service import get_route

from concurrent import futures


def eval(individual, mission, field, road):
    drones = [list(mission.drones.all().order_by('id'))[i] for i in individual[2]]
    grid, waypoints, _, initial = get_route(car_move=individual[3], direction=individual[0], height_diff=None, round_start_zone=None,
                      start=individual[1], field=field, grid_step=mission.grid_step, feature3=None, feature4=None, road=road, drones=drones)
    distance = 0
    time = 0
    drone_price, salary, penalty = 0, 0, 0
    number_of_starts = len(waypoints)
    grid_traversed = 0
    grid_total = sum([len(line) for line in grid])

    for drone_waypoints in waypoints:
        new_distance = waypoints_distance(drone_waypoints, lat_f=lambda x: x['lat'], lon_f=lambda x: x['lon'])
        new_time = waypoints_flight_time(drone_waypoints, 7,
                                         lat_f=lambda x: x['lat'], lon_f=lambda x: x['lon'],
                                         max_speed_f=lambda x: x['drone']['max_speed'],
                                         slowdown_ratio_f=lambda x: x['drone']['slowdown_ratio_per_degree'],
                                         min_slowdown_ratio_f=lambda x: x['drone']['min_slowdown_ratio'],
                                         spray_on_f=lambda x: x['spray_on'])
        distance += new_distance
        time += new_time
        drone_price_n, salary_n, = drone_flight_price(drone_waypoints[0]['drone'], new_distance, new_time, mission, number_of_starts)
        drone_price += drone_price_n
        salary += salary_n
        grid_traversed += max(0, len(drone_waypoints) - 2)
    penalty = flight_penalty(time, 2, 8, salary, drone_price, grid_total, grid_traversed)
    return distance, time, drone_price, salary, penalty, number_of_starts


def run_random(mission):
    print("!!!", mission.name)
    field = json.loads(mission.field.points_serialized)
    field = [[y, x] for (x, y) in field]
    road = json.loads(mission.field.road_serialized)
    road = [[y, x] for (x, y) in road]
    number_of_drones = mission.drones.all().count()

    book = xlwt.Workbook()
    sheet_info = book.add_sheet("Results")
    sheet_info.portrait = False
    row_count = 0

    targets = []
    best_target = None
    best_individ = None
    for i in range(150 * 250):
        individual = [
            random.uniform(0, 360),
            ["ne", "nw", "se", "sw"][random.randint(0, 3)],
            [random.randint(0, number_of_drones - 1) for _ in range(random.randint(1, number_of_drones * 3))],
            [random.uniform(0, 1) for _ in range(random.randint(1, 5))]
        ]
        distance, time, drone_price, salary, penalty, number_of_starts = eval(individual, mission, field, road)
        target = drone_price + salary + penalty
        targets.append(target)
        if (not best_target) or (target < best_target):
            best_target = target
            best_individ = individual

        if i % 250 == 0:
            print("!", mission.name, i)
            sheet_info.row(row_count).write(0, i)
            sheet_info.row(row_count).write(1, best_target)
            sheet_info.row(row_count).write(2, sum(targets) / len(targets))
            sheet_info.row(row_count).write(3, str(best_individ))
            row_count += 1
    book.save(f"Random-{mission.name.replace(' ', '_')}.xls")


if __name__ == "__main__":
    with futures.ProcessPoolExecutor() as pool:
        for i in pool.map(run_random, Mission.objects.all()):
            pass
