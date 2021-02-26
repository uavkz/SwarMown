import numpy as np
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

from mainapp.utils import unique, euclidean


def get_grid(field, step):
    grid = []
    min_x = min((p[0] for p in field))
    min_y = min((p[1] for p in field))
    max_x = max((p[0] for p in field))
    max_y = max((p[1] for p in field))
    polygon = Polygon(field)

    for x in np.linspace(min_x, max_x, round((max_x - min_x) / step)):
        line = []
        for y in np.linspace(min_y, max_y, round((max_y - min_y) / step)):
            point = Point(x, y)
            if polygon.contains(point):
                line.append([x, y])
        grid.append(line)
    return grid


def get_initial_position(field, grid, road):
    #  TODO read from database
    # X/Long, Y/Lat
    return [min([f[0] for f in field]),
            min([f[1] for f in field])]


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
    zamboni_path = np.array(zamboni_path)
    track_drone_d = euclidean(zamboni_path[init_coord, 0], track_1[0], zamboni_path[init_coord, 1], track_1[1])
    max_d = max_d - track_drone_d
    i = init_coord
    left_on, ind = None, 0  # TODO FIX THIS SHIT
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
    zamboni_path = np.array(zamboni_path)
    for i in range(len(zamboni_path[init:final]) - 1):
        d = euclidean(zamboni_path[i, 0], zamboni_path[i + 1, 0], zamboni_path[i, 1], zamboni_path[i + 1, 1])
        total_dist += d
    return total_dist


# One field fly paths for all pools
def all_pools_flight(truck_stops, max_drone_flight, right_edges, path_coords):
    init_p = 0
    pool_ends = list()
    pools_drone_n = list()
    pool_drone_paths = list()
    pool_coords = list()
    flag = 0  # flag is for whether to stop on the edge to end a pool path
    for i in range(len(truck_stops) - 1):
        if i == len(truck_stops) - 2:
            flag = 1
            temp_n, temp_path, temp_coord, pool_end = \
                drones_num(truck_stops[i], truck_stops[i + 1], max_drone_flight, init_p, right_edges, path_coords, flag)
        else:
            temp_n, temp_path, temp_coord, pool_end = \
                drones_num(truck_stops[i], truck_stops[i + 1], max_drone_flight, init_p, right_edges, path_coords, flag)

        edge_ind = find_edge(truck_stops[i + 1], right_edges)  # find the coordinate where to stop one pool
        for m in range(len(path_coords)):
            if right_edges[edge_ind] == list(path_coords[m]):
                init_p = m
                break
        pool_ends.append(pool_end)

        pools_drone_n.append(temp_n)
        pool_drone_paths.append(temp_path)
        pool_coords.append(temp_coord)

    return [pools_drone_n, pool_drone_paths, pool_coords, pool_ends]


def drones_num(track_1, track_2, max_drone_flight, init_p, right_edges, path_coords, flag):
    pool_end = 0
    if flag == 0:
        edge_ind = find_edge(track_2, right_edges)  # find the coordinate where to stop one pool
        for i in range(len(path_coords)):
            if right_edges[edge_ind] == list(path_coords[i]):
                pool_end = i
    else:
        pool_end = len(path_coords) - 1  # last index to path to finish the path
    pool_start = init_p  # initial position of a drone in a new field
    total_d = total_dist(pool_start, pool_end, path_coords)  # indices of the whole path coordinates
    drones_max = 0
    drone_paths = list()
    coords = list()

    while total_d > 0:
        init_prev = init_p
        dist, coord, init_p = field_to_fly(track_1, track_2, max_drone_flight, init_prev, pool_end, path_coords)
        total_d -= dist
        drones_max += 1

        coords.append(coord)
        drone_paths.append(path_coords[init_prev:init_p + 1])

    return [drones_max, drone_paths, coords, pool_end]


def generate_zamboni(grid, drones_inits, road, number_of_drones=2):
    from mainapp.kinematic_constants import TRUCK_SPEED, DRONE_TIME
    from geopy.distance import distance

    zamboni_path = np.array(get_zigzag_path(grid))
    max_d = min_max_d(grid, const=1.1)
    right_edges = get_right_edges(zamboni_path)
    extreme_points = get_extreme_points(grid)
    y_end_km = distance(extreme_points['bottom_left'], extreme_points['top_left']).km
    x_end_km = distance(extreme_points['bottom_left'], extreme_points['bottom_right']).km
    x_end = extreme_points['bottom_right'][0]
    y_end = extreme_points['top_left'][1]
    #  TODO fix y_end and x_const values read from drones_inits and field params

    truck_path_pool = generate_stops(x_init=drones_inits[0], y_init=drones_inits[1], y_end_km=y_end_km,
                                     y_end=y_end, drone_time=DRONE_TIME,
                                     truck_V=TRUCK_SPEED, x_const=drones_inits[0],
                                     grid=grid, x_end_km=x_end_km, y_const=drones_inits[1], x_end=x_end)

    total_pathways, truck_path = best_stop_num(truck_path_pool, max_d, right_edges, zamboni_path)
    pathways_num, pathways, pathways_start_end, pool_endings = all_pools_flight(truck_path, max_d, right_edges,
                                                                                zamboni_path)
    drone_lifes = when_to_move_forward(truck_path, number_of_drones, pathways_num)
    final_pathes = final_path_calculations(drone_lifes, zamboni_path, pool_endings, max_d)
    waypoints = final_pathes.copy()
    for key, value in final_pathes.items():
        new_path = list()
        for row in value:
            for elem in row:
                if isinstance(elem, list):
                    new_path.append(elem)
                else:
                    for sub_elem in elem:
                        new_path.append(list(sub_elem))
        waypoints[key] = new_path
    return list(waypoints.values()), truck_path


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


def when_to_move_forward(truck_path, given_drone_num, estim_pathes):
    """
    Input:
    truck_path = [[1000, 100], [1000, 300], [1000, 500], [1000, 700]]
    given_drone_num = 2
    estim_pathes = [3,2,2] -number of pathways in each subfield

    Output:
    for drone d and field f -
    [starting point, path, ending point=starting point, path, ending point]
    """
    drones = {k: [] for k in range(given_drone_num)}  # create a dict with key to each drone

    for field in range(len(estim_pathes)):  # for every field
        circles = estim_pathes[field] // given_drone_num
        remainder = (estim_pathes[field] % given_drone_num)
        if circles > 0 and remainder > 0:  # 7 pathways and 5 drones, 7 pathways and 2 drones
            rem_init = remainder
            for i in range(given_drone_num):  # for every drone in the field
                path = list()
                path.append(truck_path[field])  # starts from 0
                path.append([1])  # fly the path
                if rem_init == 0:
                    path.append(truck_path[field + 1])
                else:
                    for j in range(circles):
                        path.append(truck_path[field])  # after flight goes to 0 j times
                        if j != circles - 1:
                            path.append([1])
                        elif j == circles - 1 and remainder > 0:
                            path.append([1])
                            remainder -= 1
                        else:
                            path.append(truck_path[field])
                    path.append(truck_path[field + 1])  # then goes to the next stop
                drones[i].append(path)

        elif circles > 0 and remainder == 0:  # 4 pathways and 2 drones
            rounds = int(estim_pathes[field] / given_drone_num)
            for i in range(given_drone_num):
                path = list()
                for j in range(rounds):
                    path.append(truck_path[field])
                    path.append([1])
                path.append(truck_path[field + 1])
                drones[i].append(path)

        else:  # 2 pathways and 3 drones
            pathways = estim_pathes[field]
            for i in range(given_drone_num):
                path = list()
                path.append(truck_path[field])  # starts from 0
                if pathways > 0:
                    path.append([1])  # fly the path
                    path.append(truck_path[field + 1])
                    pathways -= 1
                else:
                    path.append(truck_path[field])
                    path.append(truck_path[field + 1])
                drones[i].append(path)

    return drones


def is_horizontal(grid):
    """
    returns boolean field type
    """
    from sklearn.metrics.pairwise import haversine_distances
    answer = False
    x_max, y_max = max(grid, key=lambda x: x[0]), max(grid, key=lambda x: x[1])
    x_min, y_min = min(grid, key=lambda x: x[0]), min(grid, key=lambda x: x[1])

    horizontals = list(filter(lambda x: x[1] == y_min[1], grid))
    verts = list(filter(lambda x: x[0] == x_max[0], grid))

    hori_min, hori_max = sorted(horizontals)[0], sorted(horizontals)[-1]
    vert_min, vert_max = sorted(verts)[0], sorted(verts)[-1]

    if haversine_distances([hori_min, hori_max])[0][1] > haversine_distances([vert_min, vert_max])[0][1]:
        answer = True

    return answer


def generate_stops(x_init, x_end, x_end_km, y_const, y_init, y_end, y_end_km, x_const, truck_V, drone_time, grid):
    total_stops = []
    direction = 'horizontal' if is_horizontal(grid) else 'veritcal'
    for i in range(2, 5 + 2):  # how much stops to consider, choose any number of (this case 3) generated stops
        if direction == 'vertical':
            const, init, end, end_km = x_const, y_init, y_end, y_end_km
            stops = [[const, init]]
        else:
            const, init, end, end_km = y_const, x_init, x_end, x_end_km
            stops = [[init, const]]

        new = (init + truck_V * drone_time) * end / end_km  # just a condition for stop
        diff = (end - init) / i
        stop = diff + init

        if stop < new:
            for j in range(i - 1):
                if direction == 'vertical':
                    stops.append([const, np.round(stop + j * diff, 3)])
                elif direction == 'horizontal':
                    stops.append([np.round(stop + j * diff, 3), const])
            if direction == 'vertical':
                stops.append([const, end])
            elif direction == 'horizontal':
                stops.append([end, const])
            total_stops.append(stops)

    return total_stops


def best_stop_num(truck_path_pool, drone_flight, right_edges, new_coords):
    pathways_num = list()
    for i in range(len(truck_path_pool)):
        a, _, _, _ = all_pools_flight(truck_path_pool[i], drone_flight, right_edges, new_coords)
        pathways_num.append(np.sum(a))

    min_val_index = pathways_num.index(min(pathways_num))

    return [min(pathways_num), truck_path_pool[min_val_index]]


def find_coord(new_coords, to_find):
    for idx, coord in enumerate(new_coords):
        if list(coord) == to_find:
            return idx


def final_path_calculations(drone_lifes, path_coords, pool_endings, max_drone_flight):
    path_start = 0
    path_end = path_start
    lifes = drone_lifes.copy()
    for num in range(len(drone_lifes)):
        fields_number = len(drone_lifes[num])
        for field in range(fields_number):
            stops_number = len(drone_lifes[num][field]) // 2
            for stop in range(stops_number):
                for drone in range(len(lifes)):
                    drone_life = lifes.get(drone)
                    path = drone_life[field]
                    if len(path[(stop * 2) + 1]) == 1:  # if drone flies (==[1]) or stays on the place ([0,1000])

                        _, _, path_end = field_to_fly(path[stop * 2], path[(stop + 1) * 2], max_drone_flight,
                                                      path_start, pool_endings[field], path_coords)
                        drone_life[field][(stop * 2) + 1] = path_coords[path_start:path_end + 1]
                    path_start = path_end
    return lifes


def min_max_d(grid, const):
    horizontal = is_horizontal(grid)
    extremums = get_extreme_points(grid)
    bottom_left = extremums['bottom_left']
    bottom_right = extremums['bottom_right']
    top_left = extremums['top_left']
    if horizontal:
        min_max_distance = np.sqrt(
            (bottom_right[0] - bottom_left[0]) ** 2 + (top_left[1] - bottom_left[1]) ** 2) + \
                           (top_left[1] - bottom_left[1]) * const
    else:
        min_max_distance = np.sqrt((bottom_right[0] - bottom_left[0]) ** 2 + (top_left[1] - bottom_left[1]) ** 2) + \
                           (bottom_right[0] - bottom_left[0]) * const

    return min_max_distance


def get_extreme_points(grid):
    output = dict()
    output['bottom_left'] = np.array([min([f[0] for f in grid]), min([f[1] for f in grid])])
    output['top_left'] = np.array([min([f[0] for f in grid]), max([f[1] for f in grid])])
    output['top_right'] = np.array([max([f[0] for f in grid]), max([f[1] for f in grid])])
    output['bottom_right'] = np.array([max([f[0] for f in grid]), min([f[1] for f in grid])])
    return output
