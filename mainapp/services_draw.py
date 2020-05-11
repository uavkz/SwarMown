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
                    coord = [int(zr[0][i][nj]), int(zr[1][i][nj])]
                    new_coords.append(coord)
                counter += 1
    return new_coords


def get_waypoints(grid, drones_init):
    z = get_zigzag_path(grid)
    return [
        z[len(z) // 2:],
        z[:len(z) // 2]
    ], [[drones_init[0], drones_init[1] + (0 if i < len(z) // 2 else 350)] for i, pos in enumerate(z)]


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


# def field_to_fly(track_coord, max_d, init_coord, perc_to_save, zamboni_path):
#     max_const = max_d
#     dist = 0
#     track_drone_d = euclidean(zamboni_path[init_coord, 0], track_coord[0], zamboni_path[init_coord, 1], track_coord[1])
#     max_d = max_d - track_drone_d
#     left_on, ind = None, None
#     i = init_coord
#     while max_d > (perc_to_save * max_const) and i < len(zamboni_path) - 1:  # left max_dist is larger than ..% battery left
#         d = euclidean(zamboni_path[i, 0], zamboni_path[i + 1, 0], zamboni_path[i, 1], zamboni_path[i + 1, 1])  # between two points
#         dist += d  # skolko proshel
#         if max_d >= d:
#             max_d -= d
#             left_on = [zamboni_path[i + 1, 0], zamboni_path[i + 1, 1]]
#             ind = i + 1
#
#             check_back_path = euclidean(zamboni_path[i + 1, 0], track_coord[0], zamboni_path[i + 1, 1], track_coord[1])
#             if check_back_path > max_d:
#                 left_on = [zamboni_path[i + 1, 0], zamboni_path[i + 1, 1]]
#                 ind = i + 1
#                 break
#
#         else:
#             left_on = [zamboni_path[i + 1, 0], zamboni_path[i + 1, 1]]
#             ind = i + 1
#             break
#         i += 1
#
#     #     print("left on", left_on)
#     return [dist, left_on, ind]


def field_to_fly(track_1, track_2, max_d, init_coord, pool_end, zamboni_path):
    """
    Multiple track positions version
    :param track_1:
    :param track_2:
    :param max_d:
    :param init_coord:
    :param pool_end:
    :param zamboni_path:
    :return:
    """
    dist = 0
    track_drone_d = euclidean(zamboni_path[init_coord, 0], track_1[0], zamboni_path[init_coord, 1], track_1[1])
    #     print("track-drone distance", track_drone_d)
    max_d = max_d - track_drone_d
    #     print("start", [new_coords[init_coord,0], new_coords[init_coord,1]])
    i = init_coord
    left_on, ind = None, None
    while max_d > 0 and i < pool_end:  # left max_dist is larger than ..% battery left
        d = euclidean(zamboni_path[i, 0], zamboni_path[i + 1, 0], zamboni_path[i, 1],
                      zamboni_path[i + 1, 1])  # between two points
        dist += d  # skolko proshel
        if max_d >= d:
            max_d -= d
            left_on = [zamboni_path[i + 1, 0], zamboni_path[i + 1, 1]]
            ind = i + 1
            check_back_path = euclidean(zamboni_path[i + 1, 0], track_2[0], zamboni_path[i + 1, 1], track_2[1])
            #             print("check path to truck_2", check_back_path)
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
    #     print("                   ")
    return [dist, left_on, ind]


def total_dist(init, final, zamboni_path, total_dist=0):
    for i in range(len(zamboni_path[init:final]) - 1):
        d = euclidean(zamboni_path[i, 0], zamboni_path[i + 1, 0], zamboni_path[i, 1], zamboni_path[i + 1, 1])
        total_dist += d
    return total_dist


# Calculate number of pools to fly
def pool_number(track_stops):
    return len(track_stops) - 1


# One field fly paths for all pools
def all_pools_flight(truck_stops, max_drone_flight, right_edges, path_coords):
    init_p = 0
    pools_drone_n = list()
    pool_drone_paths = list()
    pool_coords = list()
    flag = 0
    for i in range(len(truck_stops) - 1):
        if i == len(truck_stops) - 2:
            flag = 1
            temp_n, temp_path, temp_coord = \
                drones_num(truck_stops[i], truck_stops[i + 1], max_drone_flight,
                           init_p, right_edges, path_coords, flag, path_coords)
        else:
            temp_n, temp_path, temp_coord = \
                drones_num(truck_stops[i], truck_stops[i + 1], max_drone_flight,
                           init_p, right_edges, path_coords, flag, path_coords)

        edge_ind = find_edge(truck_stops[i + 1], right_edges)  # find the coordinate where to stop one pool
        for m in range(len(path_coords)):
            if right_edges[edge_ind] == list(path_coords[m]):
                init_p = m
                break

        pools_drone_n.append(temp_n)
        pool_drone_paths.append(temp_path)
        pool_coords.append(temp_coord)

    return [pools_drone_n, pool_drone_paths, pool_coords]


# def generate_zamboni(grid, drones_inits):
#     import numpy as np
#     from mainapp.kinematic_constants import TRACK_COORD, SWARM_POPULATION
#
#     zamboni_path = np.array(get_zigzag_path(grid))
#     drones_max = 0
#     total_d = total_dist(zamboni_path)
#     drone_paths = list()
#     while total_d > 0:
#         init_prev = INIT_P
#         dist, coord, init_p = field_to_fly(TRACK_COORD, MAX_D, init_prev, PERCENT, zamboni_path)
#         total_d -= dist
#         drones_max += 1
#         drone_paths.append(zamboni_path[init_prev:init_p + 1])
#     drone_paths = [[list(coords) for coords in path] + [TRACK_COORD] for path in drone_paths]
#     waypoints = drone_paths[:SWARM_POPULATION]
#     for i, path in enumerate(drone_paths[SWARM_POPULATION:]):
#         waypoints[i % SWARM_POPULATION].extend(path)
#     return waypoints, []


def drones_num(track_1, track_2, max_drone_flight, init_p, right_edges, path_coords, flag, zamboni_path):
    pool_end = 0
    if flag == 0:
        edge_ind = find_edge(track_2, right_edges)  # find the coordinate where to stop one pool
        for i in range(len(path_coords)):
            if right_edges[edge_ind] == list(path_coords[i]):
                pool_end = i
    else:
        pool_end = len(path_coords) - 1  # last index to path to finish the path

    pool_start = init_p  # initial position of a drone in a new field
    total_d = total_dist(pool_start, pool_end, zamboni_path)  # indices of the whole path coordinates
    drones_max = 0
    drone_paths = []
    coords = []

    while total_d > 0:
        init_prev = init_p
        dist, coord, init_p = field_to_fly(track_1, track_2, max_drone_flight, init_prev, pool_end, path_coords)
        total_d -= dist
        drones_max += 1

        coords.append(coord)
        drone_paths.append(zamboni_path[init_prev:init_p + 1])

    return [drones_max, drone_paths, coords]


def generate_zamboni(grid, drones_inits):
    from mainapp.kinematic_constants import TRACK_COORD, SWARM_POPULATION

    zamboni_path = np.array(get_zigzag_path(grid))
    truck_path = [[1000, 100], [1000, 200], [1000, 300], [1000, 400], [1000, 500], [1000, 600], [1000, 700]]
    # truck_path = [[200,50], [450,50], [700,50], [950,50]]
    right_edges = [[800, 100], [800, 150], [850, 200], [850, 250], [850, 300], [900, 350],
                   [900, 400], [900, 450], [950, 500], [950, 550], [950, 600], [900, 650], [850, 700]]

    a, b, c = all_pools_flight(truck_path, 1650, right_edges, zamboni_path)
    truck_path = [[0, 100], [0, 300], [0, 500], [0, 700]]
    s = [truck_path[0]]
    # add first state from track_state_0

    first_new = s.copy()
    second_new = s.copy()
    third_new = s.copy()

    first_new.extend([list(elem) for elem in b[0][0]])
    second_new.extend([list(elem) for elem in b[0][1]])
    third_new.extend([list(elem) for elem in b[0][2]])

    fourth, fifth, sixth = [list(elem) for elem in b[1][0]], \
                           [list(elem) for elem in b[1][1]], \
                           [list(elem) for elem in b[1][2]]

    for i, f in enumerate([first_new, second_new, third_new], start=2):
        f.append(truck_path[1])
        f.append(truck_path[2])
        f.extend([list(y) for y in b[i][0]])
        f.append(truck_path[-1])

    w = truck_path[:2]

    # add two states track_state_0 and track_state_1

    fourth_new = w.copy()
    fifth_new = w.copy()
    sixth_new = w.copy()

    fourth_new.extend(fourth)
    fifth_new.extend(fifth)
    sixth_new.extend(sixth)

    for i, f in enumerate([fourth_new, fifth_new, sixth_new]):
        f.append(truck_path[-2])
        f.append(truck_path[-1])

    sixth_new.extend([list(y) for y in b[-1][0]])
    sixth_new.append(truck_path[-1])

    results = [first_new, second_new, third_new, fourth_new, fifth_new, sixth_new]
    truck_path = [[0, 100], [0, 300],
                  [0, 500], [0, 700]]
    return results, truck_path


def find_edge(track_coord, right_edges):
    distance = []
    for i in range(len(right_edges)):
        distance.append(euclidean(track_coord[0], right_edges[i][0], track_coord[1], right_edges[i][1]))
    return distance.index(min(distance))
