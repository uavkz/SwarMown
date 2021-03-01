import numpy as np
import pyproj


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


def transform_to_google_map_metric(points):
    p_ll = pyproj.Proj('epsg:4326')
    # p_mt = pyproj.Proj('epsg:3857')  # metric; same as EPSG:90091, generally good Google Map
    p_mt = pyproj.Proj('epsg:4087')  # metric; Kazakhstan

    _transform_points(points, p_ll, p_mt)


def transform_to_lat_lon(points):
    p_ll = pyproj.Proj('epsg:4326')
    # p_mt = pyproj.Proj('epsg:3857')  # metric; same as EPSG:90091, generally good Google Map
    p_mt = pyproj.Proj('epsg:4087')  # metric; Kazakhstan

    _transform_points(points, p_mt, p_ll)
