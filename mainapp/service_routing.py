from itertools import repeat, cycle

from mainapp.services_draw import get_grid, get_car_waypoints, get_car_waypoints_by_ratio_list
from mainapp.utils import add_waypoint, calc_vincenty


def get_route(
    car_move, direction, height_diff, round_start_zone, start,
    field, grid_step, feature3, feature4, road, drones,
    grid=None, pyproj_transformer=None,
):
    if direction == "simple":
        angle = 45
    elif direction == "horizontal":
        angle = 0
    elif direction == "vertical":
        angle = 90
    elif type(direction) in [float, int]:
        angle = direction
    else:
        raise Exception("Not implemented")
    if grid == None:
        grid = get_grid(field, grid_step, angle, trans=pyproj_transformer)
    if type(car_move) == str:
       car_waypoints = get_car_waypoints(grid, road, how=car_move)
    elif type(car_move) == list:
        car_waypoints = get_car_waypoints_by_ratio_list(road, car_move)
    else:
        raise Exception("Not implemented")
    waypoints = get_waypoints(grid, car_waypoints, drones, start)
    return grid, waypoints, car_waypoints, car_waypoints[0]


def get_waypoints(grid, car_waypoints, drones, start):
    waypoints = []
    zamboni_iterator = iterate_zamboni(grid, start)

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
                    total_drone_distance += generate_fly_to(drone_waypoints, car_waypoint, last_point or point, drone)

                # If there's an untraversed point from previous drone - traverse it
                if last_point and first_run:
                    total_drone_distance += calc_vincenty(last_point, point, lon_first=True)
                    if total_drone_distance >= drone.max_distance_no_load:
                        last_point = point
                        break
                    add_waypoint(drone_waypoints, last_point, drone, spray_on=True)
                    first_run = False # Prevent duplicating

                last_point = point
                # If you will not be able to return - break
                if calc_vincenty(point, next_car_waypoint, lon_first=True) > (drone.max_distance_no_load - total_drone_distance):
                    break
                # print("!!! Between", calc_vincenty([drone_waypoints[-2]['lon'], drone_waypoints[-2]['lat']], point, lon_first=True))
                if len(drone_waypoints) > 1:
                    total_drone_distance += calc_vincenty([drone_waypoints[-2]['lon'], drone_waypoints[-2]['lat']], point, lon_first=True)
                add_waypoint(drone_waypoints, point, drone, spray_on=True)
            total_drone_distance += generate_fly_back(drone_waypoints, next_car_waypoint, drone)
            waypoints.append(drone_waypoints)
            if point is None:
                break
        if point is None:
            break
    waypoints = list(filter(lambda x: len(x) > 1, waypoints))
    return waypoints


def generate_fly_to(drone_waypoints, drones_init, coord_to, drone):
    add_waypoint(drone_waypoints, drones_init, drone)
    # print("!!! TO", calc_vincenty(drones_init, coord_to, lon_first=True))
    return calc_vincenty(drones_init, coord_to, lon_first=True)


def generate_fly_back(drone_waypoints, drones_init, drone):
    add_waypoint(drone_waypoints, drones_init, drone)

    try:
        # print("!!! BACK", calc_vincenty(drones_init, [drone_waypoints[-2]['lon'], drone_waypoints[-2]['lat']], lon_first=True))
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
