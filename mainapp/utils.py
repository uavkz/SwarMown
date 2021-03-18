import math

import numpy as np
import pyproj
from django.forms import model_to_dict
from vincenty import vincenty


def flatten_grid(grid):
    for line in grid:
        for coord in line:
            yield coord


def unique(list1):
    unique_list = list()
    for x in list1:
        if x not in unique_list:
            unique_list.append(x)
    return unique_list


def euclidean(x1, x2, y1, y2):
    return np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


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


def waypoints_flight_time(waypoints, lat_f=lambda x: x.lat, lon_f=lambda x: x.lon, max_speed_f=lambda x: x.drone.max_speed):
    total_time = 0
    prev_waypoint = None
    for waypoint in waypoints:
        if prev_waypoint:
            dist = calc_vincenty([lat_f(waypoint), lon_f(waypoint)], [lat_f(prev_waypoint), lon_f(prev_waypoint)])
            total_time += dist / max_speed_f(waypoint)
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
