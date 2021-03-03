from itertools import cycle

from mainapp.utils import add_waypoint, calc_vincenty


def get_waypoints(grid, drones_init, road, drones):
    waypoints = []
    zamboni_iterator = iterate_zamboni(grid)

    last_point = None
    for drone in cycle(list(drones.all())):
        drone_waypoints = []
        point = None
        total_drone_distance = 0
        for point in zamboni_iterator:
            if point is None:
                break
            if total_drone_distance == 0 and not last_point:
                total_drone_distance += generate_fly_to(drone_waypoints, drones_init, point, drone)
            if total_drone_distance == 0 and last_point:
                add_waypoint(drone_waypoints, last_point, drone)
                total_drone_distance += generate_fly_to(drone_waypoints, drones_init, last_point, drone)
            if last_point:
                total_drone_distance += calc_vincenty(last_point, point, lon_first=True)
                if total_drone_distance >= drone.max_distance_no_load:
                    last_point = point
                    break
            last_point = point
            if calc_vincenty(point, drones_init, lon_first=True) > (drone.max_distance_no_load - total_drone_distance):
                break
            # print("!!! Between", calc_vincenty([drone_waypoints[-2]['lon'], drone_waypoints[-2]['lat']], point, lon_first=True))
            total_drone_distance += calc_vincenty([drone_waypoints[-2]['lon'], drone_waypoints[-2]['lat']], point, lon_first=True)
            add_waypoint(drone_waypoints, point, drone)
        total_drone_distance += generate_fly_back(drone_waypoints, drones_init, drone)
        waypoints.append(drone_waypoints)
        if point is None:
            break
    return waypoints, drones_init


def generate_fly_to(drone_waypoints, drones_init, coord_to, drone):
    add_waypoint(drone_waypoints, drones_init, drone)
    add_waypoint(drone_waypoints, coord_to, drone)
    # print("!!! TO", calc_vincenty(drones_init, coord_to, lon_first=True))
    return calc_vincenty(drones_init, coord_to, lon_first=True)


def generate_fly_back(drone_waypoints, drones_init, drone):
    add_waypoint(drone_waypoints, drones_init, drone)

    try:
        # print("!!! BACK", calc_vincenty(drones_init, [drone_waypoints[-2]['lon'], drone_waypoints[-2]['lat']], lon_first=True))
        return calc_vincenty(drones_init, [drone_waypoints[-2]['lon'], drone_waypoints[-2]['lat']], lon_first=True)
    except:
        return 0


def iterate_zamboni(grid):
    line_n = 0
    for line in grid:
        if line_n % 2 == 1:
            line = reversed(line)
        for point in line:
            yield point
        line_n += 1
    return None
