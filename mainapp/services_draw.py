from copy import deepcopy

import numpy as np
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

from mainapp.utils import transform_to_equidistant, transform_to_lat_lon, waypoints_distance, \
    calc_vincenty, rotate


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
