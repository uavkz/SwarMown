import math

import numpy as np
from django.forms import model_to_dict
from pyproj import Transformer
from vincenty import vincenty


def flatten_grid(grid):
    for line in grid:
        yield from line


_TO_EQUIDISTANT = Transformer.from_crs("epsg:4326", "epsg:4087")
_TO_LATLON = Transformer.from_crs("epsg:4087", "epsg:4326")


def _transform_points(points, transformer):
    for point in points:
        point[0], point[1] = transformer.transform(point[0], point[1])


def transform_to_equidistant(points):
    _transform_points(points, _TO_EQUIDISTANT)


def transform_to_lat_lon(points):
    _transform_points(points, _TO_LATLON)


_drone_dict_cache = {}


def _get_drone_dict(drone):
    drone_id = drone.id if hasattr(drone, "id") else id(drone)
    cached = _drone_dict_cache.get(drone_id)
    if cached is not None and cached.get("name") == drone.name:
        return cached
    result = model_to_dict(drone)
    _drone_dict_cache[drone_id] = result
    return result


def add_waypoint(waypoints, point, drone, height=10, speed=30, acceleration=0, spray_on=False):
    waypoints.append(
        {
            "lat": point[1],
            "lon": point[0],
            "height": height,
            "drone": _get_drone_dict(drone),
            "speed": speed,
            "acceleration": acceleration,
            "spray_on": spray_on,
        }
    )


def transit_time_hours(road_a, road_b, truck_speed_kmh):
    """Truck transit time from last point of road_a to first point of road_b.

    Roads are [[lat, lon], ...]. Returns time in hours.
    """
    exit_point = road_a[-1]
    entry_point = road_b[0]
    distance_km = calc_vincenty(exit_point, entry_point)
    if distance_km is None or distance_km == 0:
        return 0.0
    return distance_km / truck_speed_kmh


def _to_latlon(p):
    """Convert any coordinate to [lat, lon] for vincenty.

    Accepts: [lat, lon] list/tuple, or dict with 'lat'/'lon' keys.
    """
    if isinstance(p, dict):
        return [p["lat"], p["lon"]]
    return [p[0], p[1]]


def calc_vincenty(p1, p2):
    """Vincenty distance in km. Both args must be [lat, lon], or dicts with lat/lon keys."""
    return vincenty(_to_latlon(p1), _to_latlon(p2))


def calc_vincenty_lonlat(p1, p2):
    """Vincenty distance in km. Both args are [lon, lat] (grid/internal format).

    Use this for grid points, Shapely coords, and any internal [lon, lat] data.
    Handles dicts with lat/lon keys as well (extracts correctly).
    """
    a = [p1["lat"], p1["lon"]] if isinstance(p1, dict) else [p1[1], p1[0]]
    b = [p2["lat"], p2["lon"]] if isinstance(p2, dict) else [p2[1], p2[0]]
    return vincenty(a, b)


def waypoints_distance(waypoints, lat_f=lambda x: x.lat, lon_f=lambda x: x.lon):
    total_distance = 0
    prev_waypoint = None
    for waypoint in waypoints:
        if prev_waypoint:
            total_distance += (
                calc_vincenty([lat_f(waypoint), lon_f(waypoint)], [lat_f(prev_waypoint), lon_f(prev_waypoint)]) * 1000
            )
        prev_waypoint = waypoint
    return total_distance


def waypoints_flight_time(
    waypoints,
    max_working_speed=100,
    lat_f=lambda x: x.lat,
    lon_f=lambda x: x.lon,
    max_speed_f=lambda x: x.drone.max_speed,
    slowdown_ratio_f=lambda x: x.drone.slowdown_ratio_per_degree,
    min_slowdown_ratio_f=lambda x: x.drone.min_slowdown_ratio,
    spray_on_f=lambda x: False,
    height_f=None,
    climb_rate=3.0,
    descent_rate=2.0,
):
    """Compute total flight time in hours.

    When height_f is provided, accounts for altitude changes:
    segment time = max(horizontal_time, vertical_time) since the drone
    moves horizontally and vertically simultaneously.
    """
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
                    # Same horizontal position — skip for horizontal time but still count vertical
                    if height_f is not None:
                        delta_h = height_f(waypoint) - height_f(prev_waypoint)
                        if delta_h > 0:
                            total_time += delta_h / climb_rate / 3600
                        elif delta_h < 0:
                            total_time += abs(delta_h) / descent_rate / 3600
                    # Update prev_waypoint for correct height tracking on next segment,
                    # but keep prev_prev_waypoint valid for angle calculation
                    prev_waypoint = waypoint
                    continue
                angle = angle_lat_lon_vectors(prev_prev_waypoint, prev_waypoint, waypoint, lat_f, lon_f)
                if angle:
                    speed = speed * max(1 - angle * slowdown_ratio, min_slowdown_ratio)
                if spray_on_f(waypoint):
                    speed = min(max_working_speed, speed)
            horizontal_time = dist / speed

            if height_f is not None:
                delta_h = height_f(waypoint) - height_f(prev_waypoint)
                if delta_h > 0:
                    vertical_time = delta_h / climb_rate / 3600
                elif delta_h < 0:
                    vertical_time = abs(delta_h) / descent_rate / 3600
                else:
                    vertical_time = 0
                total_time += max(horizontal_time, vertical_time)
            else:
                total_time += horizontal_time
        prev_prev_waypoint = prev_waypoint
        prev_waypoint = waypoint
    return total_time


def drone_flight_price(drone, distance, time, climb_meters=0, energy_per_meter_climb=0):
    """Compute drone flight price.

    When climb_meters > 0, adds energy cost for altitude gain as equivalent
    additional distance (climb_meters * energy_per_meter_climb).
    """
    drone_price = drone["price_per_cycle"] + drone["price_per_kilometer"] * distance + drone["price_per_hour"] * time
    if climb_meters > 0 and energy_per_meter_climb > 0:
        drone_price += drone["price_per_kilometer"] * climb_meters * energy_per_meter_climb
    return drone_price


def flight_penalty(time, borderline_time, max_time, salary, drone_price, total_grid, grid_traversed):
    penalty = 0
    if time > max_time:
        exponent = min(time - max_time, 10)
        penalty = (salary + drone_price) * 1000**exponent
    elif time > borderline_time and max_time > borderline_time:
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


def calc_distance_3d(p1, p2, h1, h2):
    """3D distance: Vincenty horizontal + Euclidean vertical.

    p1, p2 are [lat, lon] or dicts. Returns distance in km.
    h1, h2 are altitudes in meters.
    """
    d_horizontal_km = calc_vincenty(p1, p2)
    if d_horizontal_km is None:
        return None
    d_horizontal_m = d_horizontal_km * 1000
    d_vertical_m = abs(h2 - h1)
    return math.sqrt(d_horizontal_m**2 + d_vertical_m**2) / 1000


def waypoints_total_climb(waypoints, height_f=lambda x: x.height):
    """Total meters of positive altitude change (climb) along waypoints."""
    total_climb = 0.0
    prev_height = None
    for wp in waypoints:
        h = height_f(wp)
        if prev_height is not None and h > prev_height:
            total_climb += h - prev_height
        prev_height = h
    return total_climb


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
