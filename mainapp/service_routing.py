from itertools import repeat
from typing import Optional, Union

from gon.base import Contour, Point
from shapely.geometry import LineString, Polygon
from shapely.geometry import Point as ShapelyPoint

from mainapp.services_draw import get_car_waypoints, get_car_waypoints_by_ratio_list, get_grid
from mainapp.utils import add_waypoint, calc_vincenty, transform_to_equidistant
from mainapp.utils_triangulation_pode import divide_polygon_with_holes
from pode import Requirement


def _direction_to_angle(direction):
    """Convert a direction spec to an angle in degrees."""
    if direction == "simple":
        return 45
    elif direction == "horizontal":
        return 0
    elif direction == "vertical":
        return 90
    elif isinstance(direction, (float, int)):
        return direction
    else:
        raise ValueError(f"Unknown direction: {direction!r}")


def _resolve_car_waypoints(car_move, grid, road):
    """Resolve car waypoints from a car_move spec (string mode or ratio list)."""
    if isinstance(car_move, str):
        return get_car_waypoints(grid, road, how=car_move)
    elif isinstance(car_move, list):
        return get_car_waypoints_by_ratio_list(road, car_move)
    else:
        raise ValueError(f"Unknown car_move type: {type(car_move)}")


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
    from gon.base import Polygon

    from pode import Requirement

    if holes:
        holes = [hole for hole in holes if len(hole) >= 3]

        if not triangulation_requirements and holes:
            if num_subpolygons:
                pass  # use provided num_subpolygons as-is
            elif num_subpolygons_rel_to_holes:
                num_subpolygons = len(holes) + num_subpolygons_rel_to_holes
            else:
                num_subpolygons = len(holes) + 1
            equal_area = 1 / num_subpolygons
            triangulation_requirements = [Requirement(equal_area) for _ in range(num_subpolygons - 1)]
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
            sub_direction = direction[idx] if isinstance(direction, list) else direction
            angle = _direction_to_angle(sub_direction)

            sub_field = [[p.x, p.y] for p in subpolygon.border.vertices]
            transform_to_equidistant(sub_field)
            sub_grid = get_grid(sub_field, grid_step, angle, do_transform=False, trans=pyproj_transformer)
            for sub_i, sub_sub_grid in enumerate(sub_grid):
                if not sub_sub_grid:
                    continue
                sub_grid[sub_i] = [
                    point for point in sub_sub_grid if not any(Point(*point) in Polygon(hole) for hole in holes_gon)
                ]

            combined_grid.extend(sub_grid)
        car_waypoints = _resolve_car_waypoints(car_move, combined_grid, road)
        waypoints = get_waypoints(combined_grid, car_waypoints, drones, start, holes)
        grid = combined_grid
    else:  # No Holes
        angle = _direction_to_angle(direction)
        if grid is None:
            grid = get_grid(field, grid_step, angle, trans=pyproj_transformer)
        car_waypoints = _resolve_car_waypoints(car_move, grid, road)
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
                    if calc_vincenty(point, car_waypoint, lon_first=True) > (
                        drone.max_distance_no_load - total_drone_distance
                    ):
                        continue
                    total_drone_distance += generate_fly_to(
                        drone_waypoints, car_waypoint, last_point or point, drone, hole_polygons
                    )

                # If there's an untraversed point from previous drone - traverse it
                if last_point and first_run and path_crosses_holes(last_point, point, hole_polygons):
                    adjusted_path = adjust_path_around_holes(last_point, point, hole_polygons)
                    total_drone_distance += add_adjusted_path(drone_waypoints, adjusted_path, drone)
                    last_point = point
                    first_run = False
                    continue

                if last_point and path_crosses_holes(last_point, point, hole_polygons):
                    adjusted_path = adjust_path_around_holes(last_point, point, hole_polygons)
                    total_drone_distance += add_adjusted_path(drone_waypoints, adjusted_path, drone)
                    last_point = point
                    continue

                # Normal waypoint addition
                total_drone_distance += calc_vincenty(last_point or drone_waypoints[-1], point, lon_first=True)
                add_waypoint(drone_waypoints, point, drone, spray_on=True)
                last_point = point

                # If you will not be able to return - break
                if calc_vincenty(point, next_car_waypoint, lon_first=True) > (
                    drone.max_distance_no_load - total_drone_distance
                ):
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
        start_point = [drone_waypoints[-1]["lon"], drone_waypoints[-1]["lat"]]
        if path_crosses_holes(start_point, drones_init, hole_polygons):
            adjusted_path = adjust_path_around_holes(start_point, drones_init, hole_polygons)
            return add_adjusted_path(drone_waypoints, adjusted_path, drone)
    add_waypoint(drone_waypoints, drones_init, drone)
    if len(drone_waypoints) >= 2:
        return calc_vincenty(drones_init, [drone_waypoints[-2]["lon"], drone_waypoints[-2]["lat"]], lon_first=True)
    return 0


def iterate_zamboni(grid, start):
    if start[0] == "n":
        grid = reversed(grid)
    for line_n, line in enumerate(grid):
        if line_n % 2 == (1 if start[1] == "e" else 0):
            line = reversed(line)
        yield from line
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
    return any(path.within(hole) or path.crosses(hole) for hole in hole_polygons)


def single_segment_adjust(start_pt, end_pt, hole):
    if not path_crosses_this_hole(start_pt, end_pt, hole):
        return [start_pt, end_pt]  # No crossing => nothing to fix

    hole_boundary = hole.exterior
    boundary_coords = list(hole_boundary.coords)[:-1]

    distances_start = [ShapelyPoint(coord).distance(ShapelyPoint(start_pt)) for coord in boundary_coords]
    idx_start = distances_start.index(min(distances_start))

    distances_end = [ShapelyPoint(coord).distance(ShapelyPoint(end_pt)) for coord in boundary_coords]
    idx_end = distances_end.index(min(distances_end))

    if idx_start <= idx_end:
        ascending = boundary_coords[idx_start : idx_end + 1]
        descending = boundary_coords[idx_end:] + boundary_coords[: idx_start + 1]
    else:
        ascending = boundary_coords[idx_start:] + boundary_coords[: idx_end + 1]
        descending = boundary_coords[idx_end : idx_start + 1]

    def crosses_or_within(seg_coords):
        s = LineString(seg_coords)
        return s.crosses(hole) or s.within(hole)

    candidate_paths = []
    for seq in (ascending, descending):
        # For each possible prefix (1..all vertices)
        for i in range(1, len(seq) + 1):
            candidate = [start_pt, *seq[:i], end_pt]
            if not crosses_or_within(candidate):
                length = LineString(candidate).length
                candidate_paths.append((length, candidate))

    if not candidate_paths:
        # fallback to direct line if no detour works
        return [start_pt, end_pt]

    _, best_candidate = min(candidate_paths, key=lambda x: x[0])
    return best_candidate


def path_crosses_this_hole(start_pt, end_pt, hole):
    seg = LineString([start_pt, end_pt])
    return seg.crosses(hole) or seg.within(hole)


def adjust_path_around_holes(start_point, end_point, hole_polygons):
    final_coords = [start_point, end_point]

    # For each hole, break final_coords into segments & fix each crossing
    for hole in hole_polygons:
        new_coords = [final_coords[0]]
        for i in range(len(final_coords) - 1):
            seg_start = new_coords[-1]
            seg_end = final_coords[i + 1]

            # If this segment crosses the hole, adjust it
            if path_crosses_this_hole(seg_start, seg_end, hole):
                adjusted = single_segment_adjust(seg_start, seg_end, hole)
                # 'adjusted' is a list of points [seg_start, ..., seg_end]
                # We already have seg_start in new_coords[-1], so skip it in appending
                new_coords.extend(adjusted[1:])
            else:
                new_coords.append(seg_end)

        final_coords = new_coords

    return final_coords


def add_adjusted_path(drone_waypoints, adjusted_path, drone):
    total_distance = 0
    for idx, point in enumerate(adjusted_path):
        if idx > 0:
            total_distance += calc_vincenty(adjusted_path[idx - 1], point, lon_first=True)
        spray_on = idx == len(adjusted_path) - 1
        add_waypoint(drone_waypoints, point, drone, spray_on=spray_on)
    return total_distance
