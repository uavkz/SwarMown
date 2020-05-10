from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
import numpy as np

from mainapp.kinematic_constants import INIT_P, MAX_D, PERCENT


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


def get_initial_position(field, grid):
    return [50, 50]


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
    counter = 0

    for i in range(Y_DIM):
        for j in range(X_DIM):
            for g in range(len(grid)):
                if i % 2 == 0:
                    nj = j
                else:
                    nj = X_DIM - j - 1
                if (grid[g][0] == int(zr[0][i][nj])) and (grid[g][1] == int(zr[1][i][nj])):
                    coord = [int(zr[0][i][nj]), int(zr[1][i][nj]), "active"]
                    new_coords.append(coord)
                counter += 1
    return new_coords


def get_waypoints(grid, drones_inits):
    z = get_zigzag_path(grid)
    return [
        z[len(z) // 2:],
        z[:len(z) // 2]
    ], []


def euclidean(x1, x2, y1, y2):
    return np.sqrt((x1 - x2)**2 + (y1 - y2)**2)


# def field_to_fly(track_coord, max_d, init_coord, perc_to_save, zamboni_path):
#     max_const = max_d
#     dist = 0
#     track_drone_d = euclidean(zamboni_path[init_coord, 0], track_coord[0], zamboni_path[init_coord, 1], track_coord[1])
#     #     print("before track coords:", max_d)
#     max_d = max_d - 2 * track_drone_d
#     #     print("after track coords:", max_d)
#     left_on, ind = None, None
#     i = init_coord
#     while (max_d > (perc_to_save * max_const) and i < len(
#             zamboni_path) - 1):  # left max_dist is larger than ..% battery left
#         d = euclidean(zamboni_path[i, 0], zamboni_path[i + 1, 0], zamboni_path[i, 1],
#                       zamboni_path[i + 1, 1])  # between two points
#         dist += d  # skolko proshel
#         if max_d >= d:
#             max_d -= d
#             left_on = [zamboni_path[i + 1, 0], zamboni_path[i + 1, 1]]
#             ind = i + 1
#         #             print("left_on", left_on)
#         #             print("ind", ind)
#         else:
#             left_on = [zamboni_path[i + 1, 0], zamboni_path[i + 1, 1]]
#             ind = i + 1
#             break
#         i += 1
#
#     #     print("left on", left_on)
#     return [dist, left_on, ind]


def field_to_fly(track_coord, max_d, init_coord, perc_to_save, zamboni_path):
    max_const = max_d
    dist = 0
    track_drone_d = euclidean(zamboni_path[init_coord, 0], track_coord[0], zamboni_path[init_coord, 1], track_coord[1])
    max_d = max_d - track_drone_d
    left_on, ind = None, None
    i = init_coord
    while max_d > (perc_to_save * max_const) and i < len(zamboni_path) - 1:  # left max_dist is larger than ..% battery left
        d = euclidean(zamboni_path[i, 0], zamboni_path[i + 1, 0], zamboni_path[i, 1], zamboni_path[i + 1, 1])  # between two points
        dist += d  # skolko proshel
        if max_d >= d:
            max_d -= d
            left_on = [zamboni_path[i + 1, 0], zamboni_path[i + 1, 1]]
            ind = i + 1

            check_back_path = euclidean(zamboni_path[i + 1, 0], track_coord[0], zamboni_path[i + 1, 1], track_coord[1])
            if check_back_path > max_d:
                left_on = [zamboni_path[i + 1, 0], zamboni_path[i + 1, 1]]
                ind = i + 1
                break

        else:
            left_on = [zamboni_path[i + 1, 0], zamboni_path[i + 1, 1]]
            ind = i + 1
            break
        i += 1

    #     print("left on", left_on)
    return [dist, left_on, ind]


def total_dist(zamboni_path, total_dist=0):
    for i in range(len(zamboni_path) - 1):
        d = euclidean(zamboni_path[i, 0], zamboni_path[i + 1, 0], zamboni_path[i, 1], zamboni_path[i + 1, 1])
        total_dist += d

    return total_dist


def generate_zamboni(grid, drones_inits):
    import numpy as np
    from mainapp.kinematic_constants import TRACK_COORD, SWARM_POPULATION
    zamboni_path = np.array(get_zigzag_path(grid))
    drones_max = 0
    total_d = total_dist(zamboni_path)
    drone_paths = list()
    while total_d > 0:
        init_prev = INIT_P
        dist, coord, init_p = field_to_fly(TRACK_COORD, MAX_D, init_prev, PERCENT, zamboni_path)
        total_d -= dist
        drones_max += 1
        drone_paths.append(zamboni_path[init_prev:init_p + 1])
    drone_paths = [[list(coords) for coords in path] + [TRACK_COORD] for path in drone_paths]
    waypoints = drone_paths[:SWARM_POPULATION]
    for i, path in enumerate(drone_paths[SWARM_POPULATION:]):
        waypoints[i % SWARM_POPULATION].extend(path)
    return waypoints, []
