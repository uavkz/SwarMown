from copy import deepcopy

import numpy as np
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
from shapely.prepared import prep

from mainapp.utils import calc_vincenty, rotate, transform_to_equidistant, transform_to_lat_lon, waypoints_distance


def get_grid(field, step, angle=0, do_transform=True, trans=None):
    field = deepcopy(field)
    if do_transform:
        transform_to_equidistant(field)
    polygon = Polygon(field)
    prepared_polygon = prep(polygon)
    grid = []

    min_x = min(p[0] for p in field)
    min_y = min(p[1] for p in field)
    max_x = max(p[0] for p in field)
    max_y = max(p[1] for p in field)

    height = max_y - min_y
    width = max_x - min_x
    min_x -= height
    max_x += height
    min_y -= width
    max_y += width

    for x in np.linspace(min_x, max_x, max(round((max_x - min_x) / step), 1)):
        line = []
        for y in np.linspace(min_y, max_y, max(round((max_y - min_y) / step), 1)):
            line.append([x, y])
        grid.append(line)

    pivot_point = [(min_x + max_x) / 2, (min_y + max_y) / 2]
    for i, line in enumerate(grid):
        line = [rotate(point, pivot_point, angle) for point in line]
        line = [p for p in line if prepared_polygon.contains(Point(p[0], p[1]))]
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

    # Precompute cumulative distances once
    cumulative = [0.0]
    for j in range(1, len(road)):
        seg = calc_vincenty([road[j][1], road[j][0]], [road[j - 1][1], road[j - 1][0]]) * 1000
        cumulative.append(cumulative[-1] + seg)
    total_distance = cumulative[-1]

    car_waypoints = []
    for ratio in ratio_list:
        target_point = ratio * total_distance
        # Find segment via cumulative distances
        for j in range(1, len(road)):
            if cumulative[j] >= target_point:
                seg_len = cumulative[j] - cumulative[j - 1]
                frac = (target_point - cumulative[j - 1]) / seg_len if seg_len > 0 else 0
                point = [
                    road[j - 1][0] + (road[j][0] - road[j - 1][0]) * frac,
                    road[j - 1][1] + (road[j][1] - road[j - 1][1]) * frac,
                ]
                break
        else:
            point = [road[-1][0], road[-1][1]]
        car_waypoints.append(point)
    return car_waypoints
