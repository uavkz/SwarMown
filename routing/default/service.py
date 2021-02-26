from itertools import cycle

from haversine import haversine


def get_waypoints(grid, drones_init, road, drones):
    waypoints = []
    zamboni_iterator = iterate_zamboni(grid)

    last_point = None
    for drone in cycle(drones.all()):
        drone_waypoints = []
        point = None
        total_drone_distance = 0
        for point in zamboni_iterator:
            if point is None:
                break
            if total_drone_distance == 0 and not last_point:
                generate_fly_to(drone_waypoints, drones_init, point)
            if total_drone_distance == 0 and last_point:
                drone_waypoints.append(last_point)
                generate_fly_to(drone_waypoints, drones_init, last_point)
            if last_point:
                total_drone_distance += haversine(last_point, point)
                if total_drone_distance >= drone.max_distance_no_load:
                    last_point = point
                    break
            last_point = point
            drone_waypoints.append(point)
        generate_fly_back(drone_waypoints, drones_init)
        waypoints.append(drone_waypoints)
        if point is None:
            break
    return waypoints, drones_init


def generate_fly_to(drone_waypoints, drones_init, coord_to):
    drone_waypoints.append(drones_init)
    drone_waypoints.append(coord_to)


def generate_fly_back(drone_waypoints, drones_init):
    drone_waypoints.append(drones_init)


def iterate_zamboni(grid):
    line_n = 0
    for line in grid:
        if line_n % 2 == 1:
            line = reversed(line)
        for point in line:
            yield point
        line_n += 1
    return None