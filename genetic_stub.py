import math
from collections import defaultdict
from copy import deepcopy
from itertools import repeat

import numpy as np
import pyproj
from django.forms import model_to_dict
from shapely.geometry import Polygon, Point
from vincenty import vincenty

from mainapp.models import Mission, Field

mission = Mission.objects.get(id=...)
field = Field.objects.get(id=...)
road = field.road_serialized
max_working_speed = 7
borderline_time = 2
max_time = 8


def drone_flight_price(drone, distance, time):
    drone_price = drone['price_per_cycle'] + drone['price_per_kilometer'] * distance + drone['price_per_hour'] * time
    return drone_price


def flight_penalty(time, borderline_time, max_time, salary, drone_price, total_grid, grid_traversed):
    penalty = 0
    if time > max_time:
        penalty = (salary + drone_price) * 1000 ** min((time - max_time), 100)
    elif time > borderline_time:
        penalty = (salary + drone_price) * (time - borderline_time) / (max_time - borderline_time)

    if total_grid - grid_traversed > 3:
        penalty += 1_000_000
    return penalty


def calc_vincenty(p1, p2, lon_first=False):
    if lon_first:
        p1 = [p1[1], p1[0]]
        p2 = [p2[1], p2[0]]
    return vincenty(p1, p2)


def waypoints_distance(waypoints, lat_f=lambda x: x.lat, lon_f=lambda x: x.lon):
    total_distance = 0
    prev_waypoint = None
    for waypoint in waypoints:
        if prev_waypoint:
            total_distance += calc_vincenty([lat_f(waypoint), lon_f(waypoint)], [lat_f(prev_waypoint), lon_f(prev_waypoint)]) * 1000
        prev_waypoint = waypoint
    return total_distance


def angle_between_vectors_degrees(u, v):
    """Return the angle between two vectors in any dimension space,
    in degrees."""
    # Original
    # return np.degrees(math.acos(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v))))
    up = np.dot(u, v)
    down = np.linalg.norm(u) * np.linalg.norm(v)
    r = up / down
    r = min(r, 1)
    r = max(r, -1)
    degrees = np.degrees(math.acos(r))
    return degrees


def angle_lat_lon_vectors(a, b, c, lat_f, lon_f):
    a = (lat_f(a), lon_f(a))
    b = (lat_f(b), lon_f(b))
    c = (lat_f(c), lon_f(c))

    # Convert the points to numpy latitude/longitude radians space
    a = np.radians(np.array(a))
    b = np.radians(np.array(b))
    c = np.radians(np.array(c))

    # Vectors in latitude/longitude space
    avec = a - b
    cvec = b - c

    # Adjust vectors for changed longitude scale at given latitude into 2D space
    lat = b[0]
    avec[1] *= math.cos(lat)
    cvec[1] *= math.cos(lat)

    # Find the angle between the vectors in 2D space
    return angle_between_vectors_degrees(avec, cvec)


def waypoints_flight_time(waypoints, max_working_speed=100.0,
                          lat_f=lambda x: x.lat, lon_f=lambda x: x.lon,
                          max_speed_f=lambda x: x.drone.max_speed,
                          slowdown_ratio_f=lambda x: x.drone.slowdown_ratio_per_degree,
                          min_slowdown_ratio_f=lambda x: x.drone.min_slowdown_ratio,
                          spray_on_f=lambda x: False):
    total_time = 0
    prev_waypoint = None
    prev_prev_waypoint = None
    for waypoint in waypoints:
        if prev_waypoint:
            dist = calc_vincenty([lat_f(waypoint), lon_f(waypoint)], [lat_f(prev_waypoint), lon_f(prev_waypoint)])
            speed = max_speed_f(waypoint)
            if prev_prev_waypoint:
                slowdown_ratio = slowdown_ratio_f(waypoint)
                min_slowdown_ratio = min_slowdown_ratio_f(waypoint)
                if lat_f(waypoint) == lat_f(prev_waypoint) and lon_f(waypoint) == lon_f(prev_waypoint):
                    continue
                angle = angle_lat_lon_vectors(prev_prev_waypoint, prev_waypoint, waypoint, lat_f, lon_f)
                if angle:
                    speed = speed * max(1 - angle * slowdown_ratio, min_slowdown_ratio)
                if spray_on_f(waypoint):
                    speed = min(max_working_speed, speed)
            total_time += dist / speed
        prev_prev_waypoint = prev_waypoint
        prev_waypoint = waypoint
    return total_time


def rotate(point, origin, angle):
    """
    Rotate a point counterclockwise by a given angle around a given origin.

    The angle should be given in degrees.
    """
    angle = math.radians(angle)
    ox, oy = origin
    px, py = point

    qx = ox + math.cos(angle) * (px - ox) - math.sin(angle) * (py - oy)
    qy = oy + math.sin(angle) * (px - ox) + math.cos(angle) * (py - oy)
    return [qx, qy]


def _transform_points(points, from_proj, to_proj):
    for point in points:
        point[0], point[1] = pyproj.transform(from_proj, to_proj, point[0], point[1])


def transform_to_equidistant(points):
    p_ll = pyproj.Proj('epsg:4326')
    # p_mt = pyproj.Proj('epsg:3857')  # metric; same as EPSG:90091, generally good Google Map
    p_mt = pyproj.Proj('epsg:4087')  # metric; equidistant

    _transform_points(points, p_ll, p_mt)


def transform_to_lat_lon(points):
    p_ll = pyproj.Proj('epsg:4326')
    # p_mt = pyproj.Proj('epsg:3857')  # metric; same as EPSG:90091, generally good Google Map
    p_mt = pyproj.Proj('epsg:4087')  # metric; equidistant

    _transform_points(points, p_mt, p_ll)


def get_grid(field, step, angle=0):
    field = deepcopy(field)
    transform_to_equidistant(field)
    polygon = Polygon(field)
    grid = []

    min_x = min((p[0] for p in field))
    min_y = min((p[1] for p in field))
    max_x = max((p[0] for p in field))
    max_y = max((p[1] for p in field))

    min_x -= (max_y - min_y)
    max_x += (max_y - min_y)

    min_y -= (max_x - min_x)
    max_y += (max_x - min_x)

    for x in np.linspace(min_x, max_x, round((max_x - min_x) / step)):
        line = []
        for y in np.linspace(min_y, max_y, round((max_y - min_y) / step)):
            line.append([x, y])
        grid.append(line)

    pivot_point = [(min_x + max_x) / 2, (min_y + max_y) / 2]
    for i, line in enumerate(grid):
        line = [rotate(point, pivot_point, angle) for point in line]
        line = list(filter(lambda x: polygon.contains(Point(x[0], x[1])), line))
        transform_to_lat_lon(line)
        grid[i] = line
    return grid


def get_car_waypoints(grid, road, how):
    # X/Long, Y/Lat
    if not road:
        raise Exception("No road")
    car_waypoints = []
    if how == "no":
        car_waypoints.append(road[0])
        total_distance = waypoints_distance(road, lat_f=lambda x: x[1], lon_f=lambda x: x[0])
        middle = total_distance / 2
        dist = 0
        prev_point = None
        for point in road:
            if prev_point:
                new_dist = calc_vincenty([point[1], point[0]], [prev_point[1], prev_point[0]]) * 1000
                if dist + new_dist >= middle:
                    d_x = point[0] - prev_point[0]
                    d_y = point[1] - prev_point[1]
                    ratio = (middle - dist) / new_dist
                    point = [prev_point[0] + d_x * ratio, prev_point[1] + d_y * ratio]
                    break
                dist += new_dist
            prev_point = point
        car_waypoints.append([point[0], point[1]])
        car_waypoints.append(road[-1])
    else:
        raise Exception("Not implemented")
    return car_waypoints


def get_car_waypoints_by_ratio_list(road, ratio_list):
    # X/Long, Y/Lat
    if not road:
        raise Exception("No road")
    car_waypoints = []
    total_distance = waypoints_distance(road, lat_f=lambda x: x[1], lon_f=lambda x: x[0])
    for ratio in ratio_list:
        dist = 0
        target_point = ratio * total_distance
        prev_point = None
        for point in road:
            if prev_point:
                new_dist = calc_vincenty([point[1], point[0]], [prev_point[1], prev_point[0]]) * 1000
                if dist + new_dist >= target_point:
                    d_x = point[0] - prev_point[0]
                    d_y = point[1] - prev_point[1]
                    ratio = (target_point - dist) / new_dist
                    point = [prev_point[0] + d_x * ratio, prev_point[1] + d_y * ratio]
                    break
                dist += new_dist
            prev_point = point
        car_waypoints.append([point[0], point[1]])
    return car_waypoints


def iterate_zamboni(grid, start):
    line_n = 0
    if start[0] == "n":
        grid = reversed(grid)
    for line in grid:
        if line_n % 2 == (1 if start[1] == "e" else 0):
            line = reversed(line)
        for point in line:
            yield point
        line_n += 1
    return None


def iterate_car_waypoints(car_waypoints):
    c, prev_c = None, None
    for car_waypoint in car_waypoints:
        prev_c = c
        c = car_waypoint
        if c and prev_c:
            yield prev_c, c

    for car_waypoint in repeat(car_waypoints[-1]):
        prev_c = c
        c = car_waypoint
        yield prev_c, c


def generate_fly_to(drone_waypoints, drones_init, coord_to, drone):
    add_waypoint(drone_waypoints, drones_init, drone)
    return calc_vincenty(drones_init, coord_to, lon_first=True)


def generate_fly_back(drone_waypoints, drones_init, drone):
    add_waypoint(drone_waypoints, drones_init, drone)

    try:
        return calc_vincenty(drones_init, [drone_waypoints[-2]['lon'], drone_waypoints[-2]['lat']], lon_first=True)
    except:
        return 0


def add_waypoint(waypoints, point, drone, height=10, speed=30, acceleration=0, spray_on=False):
    waypoints.append(
        {
            "lat": point[1],
            "lon": point[0],
            "height": height,
            "drone": model_to_dict(drone),
            "speed": speed,
            "acceleration": acceleration,
            "spray_on": spray_on,
        }
    )


def get_waypoints(grid, car_waypoints, drones, start):
    waypoints = []
    zamboni_iterator = iterate_zamboni(grid, start)

    last_point = None
    for car_waypoint, next_car_waypoint in iterate_car_waypoints(car_waypoints):
        point = None
        for drone in drones:
            drone_waypoints = []
            point = None
            total_drone_distance = 0
            first_run = True
            for point in zamboni_iterator:
                # No more points, all traversed
                if point is None:
                    break

                # Generate fly_to, if it's the first point to traverse by a drone
                if total_drone_distance == 0:
                    if calc_vincenty(point, car_waypoint, lon_first=True) > (drone.max_distance_no_load - total_drone_distance):
                        continue
                    total_drone_distance += generate_fly_to(drone_waypoints, car_waypoint, last_point or point, drone)

                # If there's an untraversed point from previous drone - traverse it
                if last_point and first_run:
                    total_drone_distance += calc_vincenty(last_point, point, lon_first=True)
                    if total_drone_distance >= drone.max_distance_no_load:
                        last_point = point
                        break
                    add_waypoint(drone_waypoints, last_point, drone, spray_on=True)
                    first_run = False # Prevent duplicating

                last_point = point
                # If you will not be able to return - break
                if calc_vincenty(point, next_car_waypoint, lon_first=True) > (drone.max_distance_no_load - total_drone_distance):
                    break
                # print("!!! Between", calc_vincenty([drone_waypoints[-2]['lon'], drone_waypoints[-2]['lat']], point, lon_first=True))
                if len(drone_waypoints) > 1:
                    total_drone_distance += calc_vincenty([drone_waypoints[-2]['lon'], drone_waypoints[-2]['lat']], point, lon_first=True)
                add_waypoint(drone_waypoints, point, drone, spray_on=True)
            total_drone_distance += generate_fly_back(drone_waypoints, next_car_waypoint, drone)
            waypoints.append(drone_waypoints)
            if point is None:
                break
        if point is None:
            break
    waypoints = list(filter(lambda x: len(x) > 1, waypoints))
    return waypoints


def get_route(car_move, direction, height_diff, round_start_zone, start,
              field, grid_step, feature3, feature4, road, drones):
    if direction == "simple":
        angle = 45
    elif direction == "horizontal":
        angle = 0
    elif direction == "vertical":
        angle = 90
    elif type(direction) in [float, int]:
        angle = direction
    else:
        raise Exception("Not implemented")
    grid = get_grid(field, grid_step, angle)
    if type(car_move) == str:
       car_waypoints = get_car_waypoints(grid, road, how=car_move)
    elif type(car_move) == list:
        car_waypoints = get_car_waypoints_by_ratio_list(road, car_move)
    else:
        raise Exception("Not implemented")
    waypoints = get_waypoints(grid, car_waypoints, drones, start)
    return grid, waypoints, car_waypoints, car_waypoints[0]


def eval(individual):
    drones = [list(mission.drones.all().order_by('id'))[i] for i in individual[2]]
    grid, waypoints, _, initial = get_route(car_move=individual[3], direction=individual[0], height_diff=None, round_start_zone=None,
                      start=individual[1], field=field, grid_step=mission.grid_step, feature3=None, feature4=None, road=road, drones=drones)
    distance = 0
    drone_price, salary, penalty = 0, 0, 0
    number_of_starts = len(waypoints)
    grid_traversed = 0
    grid_total = sum([len(line) for line in grid])

    drone_flight_time = defaultdict(int)
    for drone_waypoints in waypoints:
        new_distance = waypoints_distance(drone_waypoints, lat_f=lambda x: x['lat'], lon_f=lambda x: x['lon'])
        new_time = waypoints_flight_time(drone_waypoints, float(max_working_speed),
                                         lat_f=lambda x: x['lat'], lon_f=lambda x: x['lon'],
                                         max_speed_f=lambda x: x['drone']['max_speed'],
                                         slowdown_ratio_f=lambda x: x['drone']['slowdown_ratio_per_degree'],
                                         min_slowdown_ratio_f=lambda x: x['drone']['min_slowdown_ratio'],
                                         spray_on_f=lambda x: x['spray_on'])
        distance += new_distance
        drone_flight_time[drone_waypoints[0]['drone']['id']] += new_time + (15 / 60)
        drone_price_n = drone_flight_price(drone_waypoints[0]['drone'], new_distance, new_time)
        drone_price += drone_price_n
        grid_traversed += max(0, len(drone_waypoints) - 2)

    time = max(drone_flight_time.values())
    salary = mission.hourly_price * time * len(drone_flight_time) + mission.start_price * number_of_starts
    penalty = flight_penalty(time, float(borderline_time), float(max_time), salary, drone_price, grid_total, grid_traversed)
    return distance, time, drone_price, salary, penalty, number_of_starts
