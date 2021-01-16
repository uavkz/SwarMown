def field_to_fly(car_1, car_2, max_d, init_coord, pool_end, zigzag_path):  # TODO вынесу в Area class

    dist = 0
    ind = None
    left_on = None
    i = init_coord

    car_drone_d = euclidean(zigzag_path[init_coord][0], car_1[0], zigzag_path[init_coord][1], car_1[1])
    max_d = max_d - car_drone_d
    while max_d > 0 and i < pool_end:  # left max_dist is larger than ..% battery left
        d = euclidean(zigzag_path[i][0], zigzag_path[i + 1][0], zigzag_path[i][1],
                      zigzag_path[i + 1][1])  # between two points
        dist += d  # skolko proshel
        if max_d >= d:
            max_d -= d
            left_on = [zigzag_path[i + 1][0], zigzag_path[i + 1][1]]
            ind = i + 1
            check_back_path = euclidean(zigzag_path[i + 1][0], car_2[0], zigzag_path[i + 1][1], car_2[1])
            if check_back_path > max_d:
                break
        else:
            left_on = [zigzag_path[i + 1][0], zigzag_path[i + 1][1]]
            ind = i + 1
            break
        i += 1

    return [dist, left_on, ind]


# claculate the number of drones need to fly one pool
def drones_num(car_1, car_2, max_drone_flight, init_p, right_edges, path_coords, flag):
    if flag == 0:
        pool_end = where_to_stop_subf(car_2, right_edges, path_coords)
    else:
        pool_end = len(path_coords) - 1  # last index to path to finish the path

    pool_start = init_p
    drone_paths = []
    coords = []
    drones_max = 0

    total_d = total_dist(pool_start, pool_end, path_coords)  # indices of the whole path coordinates
    while (total_d > 0):
        init_prev = init_p
        dist, coord, init_p = field_to_fly(car_1, car_2, max_drone_flight, init_prev, pool_end, path_coords)
        total_d -= dist
        drones_max += 1
        coords.append(coord)
        drone_paths.append(path_coords[init_prev:init_p + 1])

    return [drones_max, drone_paths, coords, pool_end]


# One field fly paths for all pools
def all_pools_flight(car_stops, max_drone_flight, right_edges, path_coords):
    '''
    Every pool starts at some init_p index
    '''
    init_p = 0
    pool_ends = []
    pools_drone_n = []
    pool_drone_paths = []
    pool_coords = []
    subfields = len(car_stops) - 1
    flag = 0  # flag is for whether to stop on the last edge to end a whole pool path
    for i in range(subfields):
        if i == subfields - 1:  # if its a penultimate stop, then flag=1
            flag = 1
        temp_n, temp_path, temp_coord, pool_end = \
            drones_num(car_stops[i], car_stops[i + 1], max_drone_flight, init_p, right_edges, path_coords, flag)
        init_p = where_to_stop_subf(car_stops[i + 1], right_edges, path_coords)

        pool_ends.append(pool_end)
        pools_drone_n.append(temp_n)
        pool_drone_paths.append(temp_path)
        pool_coords.append(temp_coord)

    return [pools_drone_n, pool_drone_paths, pool_coords, pool_ends]


def extra_path_cycle(estim_pathes, given_drone_num, truck_path, drones, remainder, field, circles):
    rem_init = remainder
    for i in range(given_drone_num):  # for every drone in the field
        path = []
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

    return drones


def full_cycle(estim_pathes, given_drone_num, truck_path, drones, field):  # нельзя редачить то что приходит
    # в параметрах
    rounds = int(estim_pathes[field] / given_drone_num)
    for i in range(given_drone_num):
        path = []
        for _ in range(rounds):
            path.append(truck_path[field])
            path.append([1])
        path.append(truck_path[field + 1])
        drones[i].append(path)

    return drones


def extra_drone_cycle(estim_pathes, given_drone_num, truck_path, drones, field):  # нельзя редачить то что приходит
    # в параметрах
    pathways = estim_pathes[field]
    for i in range(given_drone_num):
        path = []
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


def when_to_move_forward(truck_path, given_drone_num, estim_pathes):
    '''
    Input:
    truck_path = [[1000, 100], [1000, 300], [1000, 500], [1000, 700]]
    given_drone_num = 2
    estim_pathes = [3,2,2] -number of pathways in each subfield

    Output:
    for drone d and field f -
    [starting point, path, ending point=starting point, path, ending point]
    '''
    drones = {k: [] for k in range(given_drone_num)}  # create a dict with key to each drone

    for field in range(len(estim_pathes)):  # for every field
        circles = estim_pathes[field] // given_drone_num
        remainder = (estim_pathes[field] % given_drone_num)

        if circles > 0 and remainder > 0:  # 7 pathways and 5 drones, 7 pathways and 2 drones
            drones = extra_path_cycle(estim_pathes, given_drone_num, truck_path, drones, remainder, field, circles)

        elif circles > 0 and remainder == 0:  # 4 pathways and 2 drones
            drones = full_cycle(estim_pathes, given_drone_num, truck_path, drones, field)

        else:  # 2 pathways and 3 drones
            drones = extra_drone_cycle(estim_pathes, given_drone_num, truck_path, drones, field)

    return drones


def generate_stops(x_init, x_end, x_end_km, y_const, y_init, y_end, y_end_km, x_const, truck_V, drone_time, direction,
                   iters):
    total_stops = []

    for i in range(2, iters + 2):  # how much stops to consider, choose any number of (this case 5) generated stops
        if direction == 'vertical':
            const, init, end, end_km = x_const, y_init, y_end, y_end_km
            stops = [[const, init]]
        elif direction == 'horizontal':
            const, init, end, end_km = y_const, x_init, x_end, x_end_km
            stops = [[init, const]]

        new = (init + truck_V * drone_time) * end / end_km  # condition for stop
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


def best_stop_num(truck_path_pool, max_drone_flight, right_edges, new_coords):
    pathways_num = []
    for i in range(len(truck_path_pool)):
        a, _, _, _ = all_pools_flight(truck_path_pool[i], max_drone_flight, right_edges, new_coords)
        pathways_num.append(np.sum(a))

    min_val_index = pathways_num.index(min(pathways_num))

    return [min(pathways_num), truck_path_pool[min_val_index]]


def final_path_calculations(drone_lifes, path_coords, pool_endings, max_drone_flight):
    # drone_lifes = commands when to move forward
    path_start = 0
    drone_paths = []
    field_paths = []
    lifes = drone_lifes.deepcopy()

    for num in range(len(drone_lifes)):  # number of drones
        fields_number = len(drone_lifes[num])
        for field in range(fields_number):  # number of subfields
            stops_number = len(drone_lifes[num][field]) // 2
            for stop in range(stops_number):  # number of pathways or stops after them
                for drone in range(len(lifes)):  # number of drones
                    drone_life = lifes.get(drone)
                    path = drone_life[field]
                    if len(drone_life[field][(
                                                     stop * 2) + 1]) == 1:  # if drone flies (==[1]) or stays on the place coordinate:([0,1000])
                        dist, drone_path, path_end = field_to_fly(path[stop * 2], path[(stop + 1) * 2],
                                                                  max_drone_flight, path_start, pool_endings[field],
                                                                  path_coords)
                        drone_life[field][(stop * 2) + 1] = path_coords[path_start:path_end + 1]
                    path_start = path_end

    return lifes