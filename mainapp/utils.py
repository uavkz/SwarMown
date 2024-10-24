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
        try:
            p1 = [p1[1], p1[0]]
        except:
            p1 = [p1['lon'], p1['lat']]
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


def waypoints_flight_time(waypoints, max_working_speed=100,
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


def latlong_to_3d(latr, lonr):
    """Convert a point given latitude and longitude in radians to
    3-dimensional space, assuming a sphere radius of one."""
    return np.array((
        math.cos(latr) * math.cos(lonr),
        math.cos(latr) * math.sin(lonr),
        math.sin(latr)
    ))


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
