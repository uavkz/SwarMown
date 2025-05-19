import argparse
import datetime
import json
import math
import random
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from itertools import repeat
from typing import Union, Optional

import matplotlib.pyplot as plt
import numpy as np
import pyproj
from deap import creator, base, tools, algorithms
from django.forms import model_to_dict
from gon.base import Point, Polygon, Contour, EMPTY, Multipolygon, Triangulation
from pyproj import Transformer
from scoop import futures
from shapely.geometry import LineString, Polygon, Point as ShapelyPoint
from vincenty import vincenty

from mainapp.models import Mission
from mainapp.utils_excel import log_excel
from pode import divide, Requirement
from pode.pode import Requirement


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


def calc_vincenty(p1, p2, lon_first=False):
    if lon_first:
        p1 = [p1[1], p1[0]]
        p2 = [p2[1], p2[0]]
    return vincenty(p1, p2)


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


def waypoints_distance(waypoints, lat_f=lambda x: x.lat, lon_f=lambda x: x.lon):
    total_distance = 0
    prev_waypoint = None
    for waypoint in waypoints:
        if prev_waypoint:
            total_distance += calc_vincenty([lat_f(waypoint), lon_f(waypoint)], [lat_f(prev_waypoint), lon_f(prev_waypoint)]) * 1000
        prev_waypoint = waypoint
    return total_distance


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



def remove_overlaps(
    original_polygon: Polygon,
    partitions: list[Polygon],
) -> list[Polygon]:
    """
    Removes overlapping areas from partitions to ensure that:
    - All partitions are mutually exclusive (no overlaps).
    - The union of all partitions equals the original polygon.

    Parameters:
    - original_polygon (Polygon): The original polygon to be partitioned.
    - partitions (List[Polygon]): The list of partitioned polygons which may have overlaps.

    Returns:
    - cleaned_partitions (List[Polygon]): The list of partitions without overlaps, covering the original polygon.
    """
    cleaned_partitions = []
    covered_area = EMPTY
    for part in partitions:
        # Subtract the already covered area to get the non-overlapping part
        non_overlapping = part - covered_area
        if non_overlapping != EMPTY:
            cleaned_partitions.append(non_overlapping)
            # Update the covered area
            covered_area |= non_overlapping
    # Identify any missing areas that weren't covered by the partitions
    missing_area = original_polygon - covered_area
    if missing_area != EMPTY:
        if isinstance(missing_area, Polygon):
            cleaned_partitions.append(missing_area)
        elif isinstance(missing_area, Multipolygon):
            cleaned_partitions.extend(missing_area.polygons)
        else:
            # Handle other geometry types if necessary
            pass
    return cleaned_partitions


def divide_polygon_with_holes(
    polygon_with_holes: Polygon,
    requirements: list[Requirement],
    verbose: bool = False,
) -> list[Polygon]:
    convex_divisor = Triangulation.constrained_delaunay

    parts = divide(
        polygon_with_holes,
        requirements,
        convex_divisor=convex_divisor,
    )
    if verbose:
        for i, part in enumerate(parts, start=1):
            print(f"Partition {i}:")
            print(f"Area: {float(part.area)}")
            anchor_point = requirements[i - 1].point
            contains_anchor = anchor_point in part if anchor_point else 'N/A'
            print(f"Contains anchor point: {contains_anchor}")
            print(f"Coordinates: {part.border.vertices}\n")

            ####### There can be overlaps :/
            original_area = polygon_with_holes.area
            parts_areas = [part.area for part in parts]
            total_parts_area = sum(parts_areas)
            area_difference = original_area - total_parts_area

            print(f"Original polygon area: {float(original_area)}")
            print(f"Total area of partitions: {float(total_parts_area)}")
            print(f"Difference in area: {float(area_difference)}")


    cleaned_parts = remove_overlaps(polygon_with_holes, parts)
    if verbose:
        # Compute area again
        original_area = polygon_with_holes.area
        parts_areas = [part.area for part in cleaned_parts]
        total_parts_area = sum(parts_areas)
        area_difference = original_area - total_parts_area

        print(f"Original polygon area: {float(original_area)}")
        print(f"Total area of partitions: {float(total_parts_area)}")
        print(f"Difference in area: {float(area_difference)}")
    return cleaned_parts


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


def get_grid(field, step, angle=0, do_transform=True, trans=None):
    field = deepcopy(field)
    if do_transform:
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
        if trans is None:
            transform_to_lat_lon(line)
        else:
            for point in line:
                point[0], point[1] = trans.transform(point[1], point[0])
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


def get_route(
    car_move,
    direction: Union[str, float, list[Union[str, float]]],
    start: Union[str, list[str]],
    field,
    grid_step,
    road,
    drones,
    grid=None,
    pyproj_transformer=None,
    holes: Optional[list[list[list[float]]]] = None,  # Same length as triangulation_requirements

    # Either one of those 3 has to be provided if holes are present
    triangulation_requirements: Optional[list[Requirement]] = None,
    num_subpolygons: Optional[int] = None,
    num_subpolygons_rel_to_holes: Optional[int] = None,
    ### OR simple_holes_traversal enabled
    simple_holes_traversal: bool = False,
    ###

    subpolygons_traversal_order: Optional[list[int]] = None,  # Same length as triangulation_requirements
):
    # This prevents really strange namespace/scope issues
    # Same issue which is partially addressed by monkey patch in settings.py
    from pode import Requirement
    from gon.base import Point, Polygon, Contour

    if holes:
        holes = [hole for hole in holes if len(hole) >= 3]

        if not triangulation_requirements and holes:
            if num_subpolygons:
                num_subpolygons = num_subpolygons
            elif num_subpolygons_rel_to_holes:
                num_subpolygons = len(holes) + num_subpolygons_rel_to_holes
            else:
                num_subpolygons = len(holes) + 1
            equal_area = 1 / num_subpolygons
            triangulation_requirements = [
                Requirement(equal_area) for _ in range(num_subpolygons - 1)
            ]
            triangulation_requirements.append(Requirement(1 - sum(equal_area for _ in range(num_subpolygons - 1))))

        outer_boundary = Contour([Point(*coord) for coord in field])
        holes_gon = [Contour([Point(*coord) for coord in hole]) for hole in holes]
        polygon_with_holes = Polygon(outer_boundary, holes_gon)
        if not simple_holes_traversal:
            subpolygons = divide_polygon_with_holes(polygon_with_holes, triangulation_requirements)
            if subpolygons_traversal_order:
                subpolygons_ordered = [subpolygons[i] for i in subpolygons_traversal_order]
            else:
                subpolygons_ordered = subpolygons
        else:
            subpolygons_ordered = [polygon_with_holes]

        combined_grid = []
        for idx, subpolygon in enumerate(subpolygons_ordered):
            if isinstance(direction, list):
                sub_direction = direction[idx]
            else:
                sub_direction = direction

            # Process direction as before
            if sub_direction == "simple":
                angle = 45
            elif sub_direction == "horizontal":
                angle = 0
            elif sub_direction == "vertical":
                angle = 90
            elif isinstance(sub_direction, (float, int)):
                angle = sub_direction
            else:
                raise Exception("Not implemented")

            sub_field = [[p.x, p.y] for p in subpolygon.border.vertices]
            transform_to_equidistant(sub_field)
            sub_grid = get_grid(sub_field, grid_step, angle, do_transform=False, trans=pyproj_transformer)
            for sub_i, sub_sub_grid in enumerate(sub_grid):
                if not sub_sub_grid:
                    continue
                sub_grid[sub_i] = [point for point in sub_sub_grid if not any(Point(*point) in Polygon(hole) for hole in holes_gon) ]

            combined_grid.extend(sub_grid)
        if isinstance(car_move, str):
            car_waypoints = get_car_waypoints(grid, road, how=car_move)
        elif isinstance(car_move, list):
            car_waypoints = get_car_waypoints_by_ratio_list(road, car_move)
        else:
            raise Exception("Not implemented")
        waypoints = get_waypoints(
            combined_grid, car_waypoints, drones, start, holes
        )
        grid = combined_grid
    else:  # No Holes
        if direction == "simple":
            angle = 45
        elif direction == "horizontal":
            angle = 0
        elif direction == "vertical":
            angle = 90
        elif isinstance(direction, (float, int)):
            angle = direction
        else:
            raise Exception("Not implemented")
        if grid is None:
            grid = get_grid(field, grid_step, angle, trans=pyproj_transformer)
        if isinstance(car_move, str):
            car_waypoints = get_car_waypoints(grid, road, how=car_move)
        elif isinstance(car_move, list):
            car_waypoints = get_car_waypoints_by_ratio_list(road, car_move)
        else:
            raise Exception("Not implemented")
        waypoints = get_waypoints(grid, car_waypoints, drones, start)
    return grid, waypoints, car_waypoints, car_waypoints[0]


def get_waypoints(grid, car_waypoints, drones, start, holes=None):
    waypoints = []
    zamboni_iterator = iterate_zamboni(grid, start)

    hole_polygons = [Polygon(hole) for hole in holes] if holes else []
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
                    total_drone_distance += generate_fly_to(drone_waypoints, car_waypoint, last_point or point, drone, hole_polygons)

                # If there's an untraversed point from previous drone - traverse it
                if last_point and first_run:
                    if path_crosses_holes(last_point, point, hole_polygons):
                        adjusted_path = adjust_path_around_holes(last_point, point, hole_polygons)
                        total_drone_distance += add_adjusted_path(drone_waypoints, adjusted_path, drone)
                        last_point = point
                        first_run = False
                        continue

                if last_point:
                    if path_crosses_holes(last_point, point, hole_polygons):
                        adjusted_path = adjust_path_around_holes(last_point, point, hole_polygons)
                        total_drone_distance += add_adjusted_path(drone_waypoints, adjusted_path, drone)
                        last_point = point
                        continue

                # Normal waypoint addition
                total_drone_distance += calc_vincenty(last_point or drone_waypoints[-1], point, lon_first=True)
                add_waypoint(drone_waypoints, point, drone, spray_on=True)
                last_point = point

                # If you will not be able to return - break
                if calc_vincenty(point, next_car_waypoint, lon_first=True) > (drone.max_distance_no_load - total_drone_distance):
                    break

            if drone_waypoints:
                total_drone_distance += generate_fly_back(drone_waypoints, next_car_waypoint, drone, hole_polygons)
                waypoints.append(drone_waypoints)
            if point is None:
                break
        if point is None:
            break
    waypoints = list(filter(lambda x: len(x) > 3, waypoints))
    return waypoints


def generate_fly_to(drone_waypoints, drones_init, coord_to, drone, hole_polygons=None):
    if hole_polygons and path_crosses_holes(drones_init, coord_to, hole_polygons):
        adjusted_path = adjust_path_around_holes(drones_init, coord_to, hole_polygons)
        return add_adjusted_path(drone_waypoints, adjusted_path, drone)
    add_waypoint(drone_waypoints, drones_init, drone)
    return calc_vincenty(drones_init, coord_to, lon_first=True)


def generate_fly_back(drone_waypoints, drones_init, drone, hole_polygons=None):
    if hole_polygons and drone_waypoints:
        start_point = [drone_waypoints[-1]['lon'], drone_waypoints[-1]['lat']]
        if path_crosses_holes(start_point, drones_init, hole_polygons):
            adjusted_path = adjust_path_around_holes(start_point, drones_init, hole_polygons)
            return add_adjusted_path(drone_waypoints, adjusted_path, drone)
    add_waypoint(drone_waypoints, drones_init, drone)
    try:
        return calc_vincenty(drones_init, [drone_waypoints[-2]['lon'], drone_waypoints[-2]['lat']], lon_first=True)
    except:
        return 0


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


def path_crosses_holes(start_point, end_point, hole_polygons):
    if not hole_polygons:
        return False
    path = LineString([start_point, end_point])
    for hole in hole_polygons:
        if path.within(hole) or path.crosses(hole):
            return True
    return False


def single_segment_adjust(start_pt, end_pt, hole):
    path = LineString([start_pt, end_pt])
    if not path_crosses_this_hole(start_pt, end_pt, hole):
        return [start_pt, end_pt]  # No crossing => nothing to fix

    hole_boundary = hole.exterior
    boundary_coords = list(hole_boundary.coords)[:-1]

    distances_start = [
        ShapelyPoint(coord).distance(ShapelyPoint(start_pt))
        for coord in boundary_coords
    ]
    idx_start = distances_start.index(min(distances_start))

    distances_end = [
        ShapelyPoint(coord).distance(ShapelyPoint(end_pt))
        for coord in boundary_coords
    ]
    idx_end = distances_end.index(min(distances_end))

    if idx_start <= idx_end:
        ascending = boundary_coords[idx_start : idx_end + 1]
        descending = boundary_coords[idx_end:] + boundary_coords[: idx_start + 1]
    else:
        ascending = boundary_coords[idx_start:] + boundary_coords[: idx_end + 1]
        descending = boundary_coords[idx_end : idx_start + 1]

    def crosses_or_within(seg_coords):
        s = LineString(seg_coords)
        return s.crosses(hole) or s.within(hole)

    candidate_paths = []
    for seq in (ascending, descending):
        # For each possible prefix (1..all vertices)
        for i in range(1, len(seq) + 1):
            candidate = [start_pt] + seq[:i] + [end_pt]
            if not crosses_or_within(candidate):
                length = LineString(candidate).length
                candidate_paths.append((length, candidate))

    if not candidate_paths:
        # fallback to direct line if no detour works
        return [start_pt, end_pt]

    _, best_candidate = min(candidate_paths, key=lambda x: x[0])
    return best_candidate


def path_crosses_this_hole(start_pt, end_pt, hole):
    seg = LineString([start_pt, end_pt])
    return seg.crosses(hole) or seg.within(hole)


def adjust_path_around_holes(start_point, end_point, hole_polygons):
    final_coords = [start_point, end_point]

    # For each hole, break final_coords into segments & fix each crossing
    for hole in hole_polygons:
        new_coords = [final_coords[0]]
        for i in range(len(final_coords) - 1):
            seg_start = new_coords[-1]
            seg_end = final_coords[i + 1]

            # If this segment crosses the hole, adjust it
            if path_crosses_this_hole(seg_start, seg_end, hole):
                adjusted = single_segment_adjust(seg_start, seg_end, hole)
                # 'adjusted' is a list of points [seg_start, ..., seg_end]
                # We already have seg_start in new_coords[-1], so skip it in appending
                new_coords.extend(adjusted[1:])
            else:
                new_coords.append(seg_end)

        final_coords = new_coords

    return final_coords


def add_adjusted_path(drone_waypoints, adjusted_path, drone):
    total_distance = 0
    for idx, point in enumerate(adjusted_path):
        if idx > 0:
            total_distance += calc_vincenty(adjusted_path[idx - 1], point, lon_first=True)
        spray_on = (idx == len(adjusted_path) - 1)
        add_waypoint(drone_waypoints, point, drone, spray_on=spray_on)
    return total_distance



parser = argparse.ArgumentParser()

parser.add_argument("--mission_id", "-m", help="Mission id")
parser.add_argument("--ngen", "-n", help="Number of generations")
parser.add_argument("--population_size", "-p", help="Population size")
parser.add_argument("--filename", "-f", help="Filename for output (without extension)")
parser.add_argument("--max-time", "-t", help="Maximum time")
parser.add_argument("--borderline_time", "-b", help="Borderline time")
parser.add_argument("--max_working_speed", "-mxs", help="Max working speed")
parser.add_argument("--mutation_chance", "-mt", help="Mutation chance")
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
    # TODO
    NUM_RANDOM_INDIVS = 10
    NUM_RANDOM_REQUIREMENTS = 30

    def generate_random_requirements_sets(n):
        from pode import Requirement

        holes = json.loads(mission.field.holes_serialized)
        sets_ = []
        for _ in range(n):
            total = 1.0
            count = random.randint(len(holes) + 1, len(holes) * 2)
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

    print("Getting best requirements set", datetime.datetime.now())
    with ThreadPoolExecutor(max_workers=8) as executor: # TODO change max_workers
        results = list(executor.map(pre_eval_worker, combos))

    best_preeval = min(results, key=lambda x: x["drone_price"] + x["salary"] + x["penalty"])
    # TODO: Improve - based on max + avg per every set of requirmenets grouped
    BEST_REQS = best_preeval["req"]
    print("Best requirements set found", datetime.datetime.now())

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
