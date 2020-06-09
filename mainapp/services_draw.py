from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
import numpy as np

from mainapp.kinematic_constants import INIT_P, MAX_D, PERCENT


def get_field():
    points = [
        # X/Long, Y/Lat
        [76.85, 43.22],
        [76.86, 43.22],
        [76.86, 43.23],
        [76.862, 43.235],
        [76.85, 43.23],
    ]
    return points


def get_grid(field, step):
    grid = []
    min_x = min((p[0] for p in field))
    min_y = min((p[1] for p in field))
    max_x = max((p[0] for p in field))
    max_y = max((p[1] for p in field))
    polygon = Polygon(field)

    for x in np.linspace(min_x, max_x, round((max_x - min_x) / step)):
        for y in np.linspace(min_y, max_y, round((max_y - min_y) / step)):
            point = Point(x, y)
            if polygon.contains(point):
                grid.append([x, y])
    return grid


def get_initial_position(field, grid):
    # X/Long, Y/Lat
    return [76.85, 43.22]


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
                if (grid[g][0] == zr[0][i][nj]) and (grid[g][1] == zr[1][i][nj]):
                    coord = [zr[0][i][nj], zr[1][i][nj]]
                    new_coords.append(coord)
                counter += 1
    return new_coords


def get_waypoints(grid, drones_init):
    z = get_zigzag_path(grid)
    return [
        z[len(z) // 2:],
        z[:len(z) // 2]
    ], [[drones_init[0], drones_init[1] + (0 if i < (len(z) // 4) else 350)] for i, pos in enumerate(z)]


def euclidean(x1, x2, y1, y2):
    return np.sqrt((x1 - x2)**2 + (y1 - y2)**2)


# def field_to_fly(track_coord, max_d, init_coord, perc_to_save, zamboni_path):
#     max_const = max_d
#     dist = 0
#     track_drone_d = euclidean(zamboni_path[init_coord, 0], track_coord[0], zamboni_path[init_coord, 1], track_coord[1])
#     max_d = max_d - 2 * track_drone_d
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
#         else:
#             left_on = [zamboni_path[i + 1, 0], zamboni_path[i + 1, 1]]
#             ind = i + 1
#             break
#         i += 1
#
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
    max_d = max_d - track_drone_d
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
            if check_back_path > max_d:
                left_on = [zamboni_path[i + 1, 0], zamboni_path[i + 1, 1]]
                ind = i + 1
                break

        else:
            left_on = [zamboni_path[i + 1, 0], zamboni_path[i + 1, 1]]
            ind = i + 1
            break
        i += 1
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
                drones_num(truck_stops[i], truck_stops[i + 1], max_drone_flight, init_p, right_edges, path_coords, flag, path_coords)
        else:
            temp_n, temp_path, temp_coord = \
                drones_num(truck_stops[i], truck_stops[i + 1], max_drone_flight, init_p, right_edges, path_coords, flag, path_coords)

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
        pool_end = len(path_coords) - 1  # last index to path to finish the pathdd

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


def get_legit_a(a):
    new_idx = list()
    prev = None
    for i, val in enumerate(a):
        if not i:
            prev = val
            new_idx.append(val - 1)
        else:
            new_idx.append(prev + val - 1)
            prev += val
    return new_idx


def get_legit_waypoints(swarm_population, flatten_routes, truck_path, a):
    """
    for even drone num, fix in next iteration


    first three drones:
    1. fly
    2. go to new track coord
    3. move with car

    another three drones:
    1. move with car
    2. fly
    3. go to new track coord
    """
    way_dict = {str(k): [truck_path[0], ] for k in range(swarm_population)}
    if a[0] < len(way_dict):
        way_dict[list(way_dict.keys())[a[0] - len(way_dict)]].append(truck_path[1])
    h = 0
    new_a = get_legit_a(a)
    for i, w in enumerate(flatten_routes):
        if i <= new_a[h]:
            way_dict[str(int(i % swarm_population))].extend(flatten_routes[i])
            way_dict[str(int(i % swarm_population))].append(truck_path[1 + h])
        else:
            h += 1
            way_dict[str(int(i % swarm_population))].extend(flatten_routes[i])
            way_dict[str(int(i % swarm_population))].append(truck_path[1 + h])
    for key, value in way_dict.items():
        if value[-1] != truck_path[-1]:
            way_dict[key].append(truck_path[-1])
    return way_dict


def get_flatten_waypoints(waypoints):
    flatten_routes = list()
    for w in waypoints:
        if len(w) - 1:
            for subway in w:
                flatten_routes.append([list(el) for el in  subway])
        else:
            flatten_routes.append([list(el) for el in w[0]])
    return flatten_routes


def get_legit_truck_waypoints(truck_path, b):
    track_routes = list()
    for i, way in enumerate(b, start=1):
        sub = list()
        for w in way:
            sub.append(len(w))
        if i == 1:
            m = 20
        else:
            m = 24
        track_routes.extend([truck_path[i]] * m)
    return track_routes


def generate_zamboni(grid, drones_inits):
    from mainapp.kinematic_constants import SWARM_POPULATION

    zamboni_path = np.array(get_zigzag_path(grid))
    truck_path = truck_coords(y_init=0, y_end_km=2, y_end_coords=43.22, drone_time=0.2,
                              truck_V=30, gap_coef=0, x_coord=76.85)[1]
    right_edges = get_right_edges(zamboni_path)
    a, b, c = all_pools_flight(truck_path, 175, right_edges, zamboni_path)  # TODO fix 1750 value
    flatten_routes = get_flatten_waypoints(b)
    way_dict = get_legit_waypoints(SWARM_POPULATION, flatten_routes, truck_path, a)
    truck_ways = get_legit_truck_waypoints(truck_path, b)
    waypoints = [i[1:] for i in list(way_dict.values())]
    return waypoints, truck_ways


def find_edge(track_coord, right_edges):
    distance = []
    for i in range(len(right_edges)):
        distance.append(euclidean(track_coord[0], right_edges[i][0], track_coord[1], right_edges[i][1]))
    return distance.index(min(distance))


def get_right_edges(new_coords):
    steps = set()
    for coord in new_coords:
        steps.add(coord[1])
    steps = sorted(list(steps))
    edges = list()
    for step in steps:
        edge_max = 0
        for coord in new_coords:
            if coord[1] == step:
                if coord[0] > edge_max:
                    edge_max = coord[0]
        edges.append([edge_max, step])
    return edges


def truck_coords(y_init, y_end_km, y_end_coords, drone_time, truck_V, gap_coef, x_coord):
    y_first = y_init
    result = [[x_coord, y_init], ]
    result_coord = []

    while y_init < y_end_km:
        y_new = y_init + truck_V * drone_time
        result.append([x_coord, y_new])
        y_new, y_init = y_init, y_new

    if result[-1][-1] > y_end_km:
        result[-1] = [x_coord, y_end_km]

    for elem in result[1:]:
        result_coord.append([x_coord, elem[1] * y_end_coords / y_end_km])

    result_coord.insert(0, [x_coord, y_first])

    return result, result_coord
