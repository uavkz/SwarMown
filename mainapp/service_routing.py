from copy import deepcopy
from itertools import repeat
from typing import Union, Optional

from gon.base import Point, Polygon, Contour, EMPTY, Multipolygon, Triangulation
from shapely.geometry import LineString, Polygon, MultiPoint, Point as ShapelyPoint

from mainapp.services_draw import get_grid, get_car_waypoints, get_car_waypoints_by_ratio_list
from mainapp.utils import add_waypoint, calc_vincenty, transform_to_equidistant
from mainapp.utils_triangulation_pode import divide_polygon_with_holes
from pode import Requirement



def get_route(
    car_move,
    direction: Union[str, float, list[Union[str, float]]],
    start: Union[str, list[str]],
    field,
    grid_step,
    road,
    drones,
    grid=None,
    pyproj_transformer=None,
    holes: Optional[list[list[list[float]]]] = None,  # Same length as triangulation_requirements

    # Either one of those 3 has to be provided if holes are present
    triangulation_requirements: Optional[list[Requirement]] = None,
    num_subpolygons: Optional[int] = None,
    num_subpolygons_rel_to_holes: Optional[int] = None,
    ### OR simple_holes_traversal enabled
    simple_holes_traversal: bool = False,
    ###

    subpolygons_traversal_order: Optional[list[int]] = None,  # Same length as triangulation_requirements
):
    # This prevents really strange namespace/scope issues
    # Same issue which is partially addressed by monkey patch in settings.py
    from pode import Requirement
    from gon.base import Point, Polygon, Contour

    if holes:
        holes = [hole for hole in holes if len(hole) >= 3]

        if not triangulation_requirements and holes:
            if num_subpolygons:
                num_subpolygons = num_subpolygons
            elif num_subpolygons_rel_to_holes:
                num_subpolygons = len(holes) + num_subpolygons_rel_to_holes
            else:
                num_subpolygons = len(holes) + 1
            equal_area = 1 / num_subpolygons
            triangulation_requirements = [
                Requirement(equal_area) for _ in range(num_subpolygons - 1)
            ]
            triangulation_requirements.append(Requirement(1 - sum(equal_area for _ in range(num_subpolygons - 1))))

        outer_boundary = Contour([Point(*coord) for coord in field])
        holes_gon = [Contour([Point(*coord) for coord in hole]) for hole in holes]
        polygon_with_holes = Polygon(outer_boundary, holes_gon)
        if not simple_holes_traversal:
            subpolygons = divide_polygon_with_holes(polygon_with_holes, triangulation_requirements)
            if subpolygons_traversal_order:
                subpolygons_ordered = [subpolygons[i] for i in subpolygons_traversal_order]
            else:
                subpolygons_ordered = subpolygons
        else:
            subpolygons_ordered = [polygon_with_holes]

        combined_grid = []
        for idx, subpolygon in enumerate(subpolygons_ordered):
            if isinstance(direction, list):
                sub_direction = direction[idx]
            else:
                sub_direction = direction

            # Process direction as before
            if sub_direction == "simple":
                angle = 45
            elif sub_direction == "horizontal":
                angle = 0
            elif sub_direction == "vertical":
                angle = 90
            elif isinstance(sub_direction, (float, int)):
                angle = sub_direction
            else:
                raise Exception("Not implemented")

            sub_field = [[p.x, p.y] for p in subpolygon.border.vertices]
            transform_to_equidistant(sub_field)
            sub_grid = get_grid(sub_field, grid_step, angle, do_transform=False, trans=pyproj_transformer)
            for sub_i, sub_sub_grid in enumerate(sub_grid):
                if not sub_sub_grid:
                    continue
                sub_grid[sub_i] = [point for point in sub_sub_grid if not any(Point(*point) in Polygon(hole) for hole in holes_gon) ]

            combined_grid.extend(sub_grid)
        if isinstance(car_move, str):
            car_waypoints = get_car_waypoints(grid, road, how=car_move)
        elif isinstance(car_move, list):
            car_waypoints = get_car_waypoints_by_ratio_list(road, car_move)
        else:
            raise Exception("Not implemented")
        waypoints = get_waypoints(
            combined_grid, car_waypoints, drones, start, holes
        )
        grid = combined_grid
    else:  # No Holes
        if direction == "simple":
            angle = 45
        elif direction == "horizontal":
            angle = 0
        elif direction == "vertical":
            angle = 90
        elif isinstance(direction, (float, int)):
            angle = direction
        else:
            raise Exception("Not implemented")
        if grid is None:
            grid = get_grid(field, grid_step, angle, trans=pyproj_transformer)
        if isinstance(car_move, str):
            car_waypoints = get_car_waypoints(grid, road, how=car_move)
        elif isinstance(car_move, list):
            car_waypoints = get_car_waypoints_by_ratio_list(road, car_move)
        else:
            raise Exception("Not implemented")
        waypoints = get_waypoints(grid, car_waypoints, drones, start)
    return grid, waypoints, car_waypoints, car_waypoints[0]


def get_waypoints(grid, car_waypoints, drones, start, holes=None):
    waypoints = []
    zamboni_iterator = iterate_zamboni(grid, start)

    hole_polygons = [Polygon(hole) for hole in holes] if holes else []
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
                    total_drone_distance += generate_fly_to(drone_waypoints, car_waypoint, last_point or point, drone, hole_polygons)

                # If there's an untraversed point from previous drone - traverse it
                if last_point and first_run:
                    if path_crosses_holes(last_point, point, hole_polygons):
                        adjusted_path = adjust_path_around_holes(last_point, point, hole_polygons)
                        total_drone_distance += add_adjusted_path(drone_waypoints, adjusted_path, drone)
                        last_point = point
                        first_run = False
                        continue

                if last_point:
                    if path_crosses_holes(last_point, point, hole_polygons):
                        adjusted_path = adjust_path_around_holes(last_point, point, hole_polygons)
                        total_drone_distance += add_adjusted_path(drone_waypoints, adjusted_path, drone)
                        last_point = point
                        continue

                # Normal waypoint addition
                total_drone_distance += calc_vincenty(last_point or drone_waypoints[-1], point, lon_first=True)
                add_waypoint(drone_waypoints, point, drone, spray_on=True)
                last_point = point

                # If you will not be able to return - break
                if calc_vincenty(point, next_car_waypoint, lon_first=True) > (drone.max_distance_no_load - total_drone_distance):
                    break

            if drone_waypoints:
                total_drone_distance += generate_fly_back(drone_waypoints, next_car_waypoint, drone, hole_polygons)
                waypoints.append(drone_waypoints)
            if point is None:
                break
        if point is None:
            break
    waypoints = list(filter(lambda x: len(x) > 3, waypoints))
    return waypoints


def generate_fly_to(drone_waypoints, drones_init, coord_to, drone, hole_polygons=None):
    if hole_polygons and path_crosses_holes(drones_init, coord_to, hole_polygons):
        adjusted_path = adjust_path_around_holes(drones_init, coord_to, hole_polygons)
        return add_adjusted_path(drone_waypoints, adjusted_path, drone)
    add_waypoint(drone_waypoints, drones_init, drone)
    return calc_vincenty(drones_init, coord_to, lon_first=True)


def generate_fly_back(drone_waypoints, drones_init, drone, hole_polygons=None):
    if hole_polygons and drone_waypoints:
        start_point = [drone_waypoints[-1]['lon'], drone_waypoints[-1]['lat']]
        if path_crosses_holes(start_point, drones_init, hole_polygons):
            adjusted_path = adjust_path_around_holes(start_point, drones_init, hole_polygons)
            return add_adjusted_path(drone_waypoints, adjusted_path, drone)
    add_waypoint(drone_waypoints, drones_init, drone)
    try:
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


def path_crosses_holes(start_point, end_point, hole_polygons):
    if not hole_polygons:
        return False
    path = LineString([start_point, end_point])
    for hole in hole_polygons:
        if path.intersects(hole):
            return True
    return False


def adjust_path_around_holes(start_point, end_point, hole_polygons):
    path = LineString([start_point, end_point])
    for hole in hole_polygons:
        if path.crosses(hole) or path.within(hole):
            hole_boundary = hole.exterior
            boundary_coords = list(hole_boundary.coords)[:-1]  # Exclude the closing point

            # Find the closest vertex of the hole to the start point
            distances_start = [ShapelyPoint(coord).distance(ShapelyPoint(start_point)) for coord in boundary_coords]
            idx_start = distances_start.index(min(distances_start))

            # Find the closest vertex of the hole to the end point
            distances_end = [ShapelyPoint(coord).distance(ShapelyPoint(end_point)) for coord in boundary_coords]
            idx_end = distances_end.index(min(distances_end))

            # Generate two possible paths around the hole
            if idx_start <= idx_end:
                path1_coords = boundary_coords[idx_start:idx_end+1]
                path2_coords = boundary_coords[idx_end:] + boundary_coords[:idx_start+1]
            else:
                path1_coords = boundary_coords[idx_start:] + boundary_coords[:idx_end+1]
                path2_coords = boundary_coords[idx_end:idx_start+1]

            # Calculate lengths
            length1 = LineString([start_point] + path1_coords + [end_point]).length
            length2 = LineString([start_point] + path2_coords + [end_point]).length

            # Choose the shorter path
            hole_path = path1_coords if length1 <= length2 else path2_coords

            # Build the adjusted path
            adjusted_path = [start_point] + hole_path + [end_point]
            return adjusted_path
    return [start_point, end_point]


def add_adjusted_path(drone_waypoints, adjusted_path, drone):
    total_distance = 0
    for idx, point in enumerate(adjusted_path):
        if idx > 0:
            total_distance += calc_vincenty(adjusted_path[idx - 1], point, lon_first=True)
        spray_on = (idx == len(adjusted_path) - 1)
        add_waypoint(drone_waypoints, point, drone, spray_on=spray_on)
    return total_distance
