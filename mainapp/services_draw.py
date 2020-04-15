from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
import numpy as np


def get_field():
    points = [
        [150, 120],
        [800, 50],
        [1000, 600],
        [900, 700],
        [300, 750],

    ]
    return points


def get_grid(field, step):
    grid = []
    min_x = min((p[0] for p in field))
    min_y = min((p[1] for p in field))
    max_x = max((p[0] for p in field))
    max_y = max((p[1] for p in field))
    polygon = Polygon(field)

    for x in range(min_x, max_x, step):
        for y in range(min_y, max_y, step):
            point = Point(x, y)
            if polygon.contains(point):
                grid.append([x, y])
    return grid


def get_drones_initial_positions(field, grid):
    return [
        [0, 0],
        [0, 0],
    ]


def unique(list1):
    unique_list = []
    for x in list1:
        if x not in unique_list:
            unique_list.append(x)
    return unique_list


def convert_coordinates(a):
    a = np.array(a)
    x, y = [], []
    for b in a:
        x.append(b[0])
        y.append(b[1])
    return x, y


def get_grid_size(a):
    x, y = convert_coordinates(a)
    return len(unique(x)), len(unique(y))


def get_zigzag_path(grid):
    X_DIM, Y_DIM = get_grid_size(grid)

    x, y = convert_coordinates(grid)

    min_x = min(x)
    max_x = max(x)

    min_y = min(y)
    max_y = max(y)

    nx = np.linspace(min_x, max_x, X_DIM)
    ny = np.linspace(min_y, max_y, Y_DIM)
    zr = np.meshgrid(nx, ny)

    new_coords = []
    coord = ()
    counter = 0

    for i in range(Y_DIM):
        for j in range(X_DIM):

            for g in range(len(grid)):
                if i % 2 == 0:
                    nj = j
                else:
                    nj = X_DIM - j - 1

                if (grid[g][0] == int(zr[0][i][nj])) and (grid[g][1] == int(zr[1][i][nj])):
                    coord = [int(zr[0][i][nj]), int(zr[1][i][nj])]
                    # coord=[a[g][0],a[g][1]]
                    new_coords.append(coord)
                    coord = []
                counter += 1

    print(get_grid_size(grid))
    return new_coords


def get_waypoints(field, grid, drones_inits):
    print(grid)
    z = get_zigzag_path(grid)
    print(z)
    return [
        z[len(z) // 2:],
        z[:len(z) // 2]
    ]


def check_waypoints(a, b):
    for i in range(len(a)):
        for b in range(len(b)):
            print()
