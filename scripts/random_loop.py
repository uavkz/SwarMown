"""Random search baseline (no GA, no SCOOP — uses ProcessPoolExecutor)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")

import django

django.setup()

import json  # noqa: E402
import random  # noqa: E402
from collections import defaultdict  # noqa: E402
from concurrent import futures  # noqa: E402

import xlwt  # noqa: E402

from mainapp.models import Mission  # noqa: E402
from mainapp.service_routing import get_route  # noqa: E402
from mainapp.utils import (  # noqa: E402
    drone_flight_price,
    flight_penalty,
    waypoints_distance,
    waypoints_flight_time,
)

MAX_WORKING_SPEED = 7
BORDERLINE_TIME = 2
MAX_TIME = 8
SETUP_TIME_HOURS = 15 / 60

_WP_LAT = lambda x: x["lat"]  # noqa: E731
_WP_LON = lambda x: x["lon"]  # noqa: E731
_WP_MAX_SPEED = lambda x: x["drone"]["max_speed"]  # noqa: E731
_WP_SLOWDOWN = lambda x: x["drone"]["slowdown_ratio_per_degree"]  # noqa: E731
_WP_MIN_SLOWDOWN = lambda x: x["drone"]["min_slowdown_ratio"]  # noqa: E731
_WP_SPRAY = lambda x: x["spray_on"]  # noqa: E731


def evaluate(individual, mission, field, road):
    drones = [list(mission.drones.all().order_by("id"))[i] for i in individual[2]]
    grid, waypoints, _, _ = get_route(
        car_move=individual[3],
        direction=individual[0],
        start=individual[1],
        field=field,
        grid_step=mission.grid_step,
        road=road,
        drones=drones,
    )
    distance = 0
    drone_price, salary, penalty = 0, 0, 0
    number_of_starts = len(waypoints)
    grid_traversed = 0
    grid_total = sum(len(line) for line in grid)

    drone_flight_time = defaultdict(int)
    for drone_waypoints in waypoints:
        new_distance = waypoints_distance(drone_waypoints, lat_f=_WP_LAT, lon_f=_WP_LON)
        new_time = waypoints_flight_time(
            drone_waypoints,
            MAX_WORKING_SPEED,
            lat_f=_WP_LAT,
            lon_f=_WP_LON,
            max_speed_f=_WP_MAX_SPEED,
            slowdown_ratio_f=_WP_SLOWDOWN,
            min_slowdown_ratio_f=_WP_MIN_SLOWDOWN,
            spray_on_f=_WP_SPRAY,
        )
        distance += new_distance
        drone_flight_time[drone_waypoints[0]["drone"]["id"]] += new_time + SETUP_TIME_HOURS
        drone_price += drone_flight_price(drone_waypoints[0]["drone"], new_distance, new_time)
        grid_traversed += max(0, len(drone_waypoints) - 2)

    if not drone_flight_time:
        return 0, 0, 0, 0, 1_000_000, 0

    time = max(drone_flight_time.values())
    salary = mission.hourly_price * time * len(drone_flight_time) + mission.start_price * number_of_starts
    penalty = flight_penalty(time, BORDERLINE_TIME, MAX_TIME, salary, drone_price, grid_total, grid_traversed)
    return distance, time, drone_price, salary, penalty, number_of_starts


def run_random(mission):
    print(f"Running: {mission.name}")
    field = [[y, x] for x, y in json.loads(mission.field.points_serialized)]
    road = [[y, x] for x, y in json.loads(mission.field.road_serialized)]
    num_drones = mission.drones.all().count()

    book = xlwt.Workbook()
    sheet = book.add_sheet("Results")
    sheet.portrait = False
    row_count = 0

    targets = []
    best_target = None
    best_individ = None

    for i in range(150 * 250):
        individual = [
            random.uniform(0, 360),
            random.choice(["ne", "nw", "se", "sw"]),
            [random.randint(0, num_drones - 1) for _ in range(random.randint(1, num_drones * 3))],
            [random.uniform(0, 1) for _ in range(random.randint(1, 5))],
        ]
        _, _, drone_price, salary, penalty, _ = evaluate(individual, mission, field, road)
        target = drone_price + salary + penalty
        targets.append(target)
        if best_target is None or target < best_target:
            best_target = target
            best_individ = individual

        if i % 250 == 0:
            print(f"  {mission.name} iter {i}")
            sheet.row(row_count).write(0, i)
            sheet.row(row_count).write(1, best_target)
            sheet.row(row_count).write(2, sum(targets) / len(targets))
            sheet.row(row_count).write(3, str(best_individ))
            row_count += 1

    book.save(f"Random-{mission.name.replace(' ', '_')}.xls")


if __name__ == "__main__":
    with futures.ProcessPoolExecutor() as pool:
        for _ in pool.map(run_random, Mission.objects.all()):
            pass
