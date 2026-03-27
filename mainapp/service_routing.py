import math
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
    avoidance_config: Optional[dict] = None,
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
        waypoints = get_waypoints(combined_grid, car_waypoints, drones, start, holes, avoidance_config)
        grid = combined_grid
    else:  # No Holes
        angle = _direction_to_angle(direction)
        if grid is None:
            grid = get_grid(field, grid_step, angle, trans=pyproj_transformer)
        car_waypoints = _resolve_car_waypoints(car_move, grid, road)
        waypoints = get_waypoints(grid, car_waypoints, drones, start, avoidance_config=avoidance_config)
    return grid, waypoints, car_waypoints, car_waypoints[0]


def compute_crossing_width(start_pt, end_pt, hole):
    """Compute the distance a straight-line segment travels inside a hole polygon (meters).

    Uses projected coordinates (the hole is a Shapely Polygon in lon/lat space,
    so 'length' is in degrees — we approximate meters by scaling).
    """
    line = LineString([start_pt, end_pt])
    intersection = line.intersection(hole)
    if intersection.is_empty:
        return 0.0
    # Convert degree-length to approximate meters (rough, good enough for threshold)
    # At ~50° latitude, 1° lon ≈ 71 km, 1° lat ≈ 111 km. Average ≈ 90 km/°
    return intersection.length * 90_000


def compute_approach_angle(start_pt, end_pt):
    """Compute approach angle of a segment in degrees [0, 360).

    start_pt, end_pt are [lon, lat].
    """
    dx = end_pt[0] - start_pt[0]
    dy = end_pt[1] - start_pt[1]
    angle = math.degrees(math.atan2(dy, dx)) % 360
    return angle


def _angle_in_arc(angle, arc_start, arc_end):
    """Check if angle is within the arc [arc_start, arc_end] (mod 360).

    When arc_start == arc_end (mod 360), this is a full circle (always True).
    """
    arc_start = arc_start % 360
    arc_end = arc_end % 360
    angle = angle % 360
    if arc_start == arc_end:
        return True  # full circle or degenerate point — always matches
    if arc_start < arc_end:
        return arc_start <= angle <= arc_end
    else:
        # Arc wraps around 0
        return angle >= arc_start or angle <= arc_end


def compute_flyover_path(start_pt, end_pt, hole, fly_over_altitude, current_alt):
    """Generate waypoints to fly over an obstacle.

    Returns list of (lon, lat, altitude) tuples.
    The path: start → climb at entry → fly level over → descend at exit → end.
    """
    line = LineString([start_pt, end_pt])
    intersection = line.intersection(hole.boundary)
    if intersection.is_empty:
        return [(start_pt[0], start_pt[1], current_alt), (end_pt[0], end_pt[1], current_alt)]

    # Extract intersection points, ordered along the line
    if intersection.geom_type == "Point":
        pts = [(intersection.x, intersection.y)]
    elif intersection.geom_type == "MultiPoint":
        pts = [(p.x, p.y) for p in intersection.geoms]
    else:
        # LineString or other — use bounds
        pts = [(intersection.bounds[0], intersection.bounds[1]), (intersection.bounds[2], intersection.bounds[3])]

    # Sort by distance from start
    pts.sort(key=lambda p: (p[0] - start_pt[0]) ** 2 + (p[1] - start_pt[1]) ** 2)

    if len(pts) >= 2:
        entry_pt = pts[0]
        exit_pt = pts[-1]
    else:
        # Tangent case: line barely touches hole boundary — no real crossing
        return [(start_pt[0], start_pt[1], current_alt), (end_pt[0], end_pt[1], current_alt)]

    # Pull back entry/exit slightly before/after the hole boundary
    dx = end_pt[0] - start_pt[0]
    dy = end_pt[1] - start_pt[1]
    seg_len = math.sqrt(dx**2 + dy**2)
    if seg_len > 0:
        margin_frac = min(0.01, 0.001 / seg_len)  # tiny pullback
        entry_lon = entry_pt[0] - dx * margin_frac
        entry_lat = entry_pt[1] - dy * margin_frac
        exit_lon = exit_pt[0] + dx * margin_frac
        exit_lat = exit_pt[1] + dy * margin_frac
    else:
        entry_lon, entry_lat = entry_pt
        exit_lon, exit_lat = exit_pt

    return [
        (start_pt[0], start_pt[1], current_alt),
        (entry_lon, entry_lat, fly_over_altitude),
        (exit_lon, exit_lat, fly_over_altitude),
        (end_pt[0], end_pt[1], fly_over_altitude),  # stay high after crossing
    ]


def _should_fly_over(start_pt, end_pt, hole, hole_idx, avoidance_config, current_altitude):
    """Decide whether to fly over or go around based on strategy and params.

    Returns (fly_over: bool, fly_over_altitude: float).
    """
    strategy = avoidance_config["strategy"]
    params = avoidance_config.get("strategy_params")
    hole_heights = avoidance_config["hole_heights"]
    height_max = avoidance_config["height_max"]
    safety_margin = avoidance_config["safety_margin"]

    obstacle_height = hole_heights[hole_idx] if hole_idx < len(hole_heights) else 0
    required_alt = obstacle_height + safety_margin

    # Can't fly over if too high for our ceiling
    if required_alt > height_max:
        return False, 0

    # Already above obstacle — always fly over (free, no climb needed).
    # This overrides per-hole strategy params (e.g. B1=0) intentionally:
    # going around when already above would waste distance for zero benefit.
    if current_altitude >= required_alt:
        return True, current_altitude

    fly_over_alt = max(current_altitude, required_alt)
    fly_over_alt = min(fly_over_alt, height_max)
    gap = required_alt - current_altitude

    if strategy == "greedy":
        # Greedy: compare fly-over cost vs detour cost
        crossing_w = compute_crossing_width(start_pt, end_pt, hole)
        detour_path = single_segment_adjust(start_pt, end_pt, hole)
        detour_len = LineString(detour_path).length * 90_000  # approx meters
        direct_len = LineString([start_pt, end_pt]).length * 90_000
        detour_extra = detour_len - direct_len

        # Fly-over cost: climb gap meters + cross at altitude
        # Rough heuristic: climb cost ≈ gap * energy_multiplier, detour cost ≈ extra distance
        energy_mult = avoidance_config.get("energy_per_meter_climb", 1.5)
        flyover_cost = gap * energy_mult
        around_cost = detour_extra

        return flyover_cost < around_cost, fly_over_alt

    if params is None:
        return False, 0

    # --- GA strategies ---
    is_single = strategy.endswith("s")
    base_strategy = strategy.rstrip("s")

    def _get_param(idx, default=0):
        """Get per-hole or single param."""
        if is_single:
            # Single variant: one value for all holes
            if isinstance(params, (list, tuple)):
                return params[0] if params else default
            return params
        if isinstance(params, (list, tuple)) and idx < len(params):
            return params[idx]
        return default

    if base_strategy == "B1":
        # Binary: 0=around, 1=over
        return bool(_get_param(hole_idx, 0)), fly_over_alt

    elif base_strategy == "B2":
        # Max-climb threshold
        max_climb = _get_param(hole_idx, 0)
        return gap <= max_climb, fly_over_alt

    elif base_strategy == "B3":
        # Crossing-width threshold
        width_threshold = _get_param(hole_idx, 0)
        crossing_w = compute_crossing_width(start_pt, end_pt, hole)
        return crossing_w < width_threshold, fly_over_alt

    elif base_strategy == "B4":
        # Directional arc
        p = _get_param(hole_idx, (0, 0))
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            arc_start, arc_end = p[0], p[1]
        else:
            return False, 0
        approach_angle = compute_approach_angle(start_pt, end_pt)
        return _angle_in_arc(approach_angle, arc_start, arc_end), fly_over_alt

    elif base_strategy == "B5":
        # Max-climb + crossing-width threshold (combined)
        p = _get_param(hole_idx, (0, 0))
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            max_climb, width_threshold = p[0], p[1]
        else:
            return False, 0
        crossing_w = compute_crossing_width(start_pt, end_pt, hole)
        return gap <= max_climb and crossing_w < width_threshold, fly_over_alt

    elif base_strategy == "B6":
        # Directional arc + max-climb threshold
        p = _get_param(hole_idx, (0, 0, 0))
        if isinstance(p, (list, tuple)) and len(p) >= 3:
            arc_start, arc_end, max_climb = p[0], p[1], p[2]
        else:
            return False, 0
        approach_angle = compute_approach_angle(start_pt, end_pt)
        return (
            _angle_in_arc(approach_angle, arc_start, arc_end) and gap <= max_climb,
            fly_over_alt,
        )

    return False, 0


def _find_first_crossing_hole(start_pt, end_pt, hole_polygons):
    """Find the first hole that a segment crosses, ordered by distance from start.

    Returns (hole_idx, hole) or (None, None) if no crossing.
    """
    best_idx = None
    best_hole = None
    best_dist = float("inf")
    line = LineString([start_pt, end_pt])
    for idx, hole in enumerate(hole_polygons):
        if not path_crosses_this_hole(start_pt, end_pt, hole):
            continue
        intersection = line.intersection(hole.boundary)
        if intersection.is_empty:
            continue
        if intersection.geom_type == "Point":
            d = (intersection.x - start_pt[0]) ** 2 + (intersection.y - start_pt[1]) ** 2
        elif intersection.geom_type == "MultiPoint":
            d = min((p.x - start_pt[0]) ** 2 + (p.y - start_pt[1]) ** 2 for p in intersection.geoms)
        else:
            d = (intersection.bounds[0] - start_pt[0]) ** 2 + (intersection.bounds[1] - start_pt[1]) ** 2
        if d < best_dist:
            best_dist = d
            best_idx = idx
            best_hole = hole
    return best_idx, best_hole


def avoid_obstacle_3d(start_pt, end_pt, hole_polygons, avoidance_config, current_altitude):
    """3D obstacle avoidance: for each hole crossing, decide fly-over or detour.

    Processes holes in order of intersection along the segment (nearest first).
    Returns (adjusted_path, exit_altitude) where adjusted_path is a list of
    (lon, lat, altitude) tuples or [lon, lat] points.
    """
    if not avoidance_config or avoidance_config.get("strategy", "2d") == "2d":
        # Pure 2D: always go around
        return adjust_path_around_holes(start_pt, end_pt, hole_polygons), current_altitude

    result_coords = [(start_pt[0], start_pt[1], current_altitude)]
    current_start = start_pt
    current_alt = current_altitude

    # Iteratively find and handle the nearest crossing hole
    max_iterations = len(hole_polygons) * 2  # safety limit
    for _ in range(max_iterations):
        hole_idx, hole = _find_first_crossing_hole(current_start, end_pt, hole_polygons)
        if hole_idx is None:
            break

        fly_over, fly_alt = _should_fly_over(current_start, end_pt, hole, hole_idx, avoidance_config, current_alt)

        if fly_over:
            flyover = compute_flyover_path(current_start, end_pt, hole, fly_alt, current_alt)
            # Skip start (already in result), skip end (it's end_pt which may need more processing)
            for pt in flyover[1:-1]:
                result_coords.append(pt)
            current_alt = flyover[-1][2]  # exit altitude (stays high)
            # Continue from exit intersection point
            current_start = [flyover[-2][0], flyover[-2][1]]
        else:
            # Go around (2D detour) — detour goes from current_start to end_pt around hole
            detour = single_segment_adjust(current_start, end_pt, hole)
            if len(detour) > 2:
                # Add intermediate detour points (skip start and end_pt)
                for pt in detour[1:-1]:
                    result_coords.append((pt[0], pt[1], current_alt))
                # Continue from last detour vertex before end_pt to check remaining holes
                current_start = detour[-2]
            elif detour:
                current_start = detour[-1]
            else:
                break

    # Ensure end point is included
    last = result_coords[-1]
    if abs(last[0] - end_pt[0]) > 1e-10 or abs(last[1] - end_pt[1]) > 1e-10:
        result_coords.append((end_pt[0], end_pt[1], current_alt))

    return result_coords, current_alt


def add_3d_path(drone_waypoints, path_3d, drone):
    """Add 3D path points (lon, lat, altitude) as waypoints. Returns total distance."""
    total_distance = 0
    for idx, point in enumerate(path_3d):
        if idx > 0:
            prev = path_3d[idx - 1]
            total_distance += calc_vincenty([prev[0], prev[1]], [point[0], point[1]], lon_first=True)
        # Skip first point if it duplicates the last waypoint already added
        if idx == 0 and drone_waypoints:
            last = drone_waypoints[-1]
            if abs(last["lon"] - point[0]) < 1e-10 and abs(last["lat"] - point[1]) < 1e-10:
                continue
        height = point[2] if len(point) > 2 else 10
        spray_on = idx == len(path_3d) - 1
        add_waypoint(drone_waypoints, [point[0], point[1]], drone, height=height, spray_on=spray_on)
    return total_distance


def get_waypoints(grid, car_waypoints, drones, start, holes=None, avoidance_config=None):
    waypoints = []
    zamboni_iterator = iterate_zamboni(grid, start)

    hole_polygons = [Polygon(hole) for hole in holes] if holes else []
    use_3d = avoidance_config is not None and avoidance_config.get("strategy", "2d") != "2d"
    working_alt = avoidance_config["height_min"] if avoidance_config else 10

    last_point = None
    for car_waypoint, next_car_waypoint in iterate_car_waypoints(car_waypoints):
        point = None
        for drone in drones:
            drone_waypoints = []
            point = None
            total_drone_distance = 0
            first_run = True
            current_alt = working_alt  # reset altitude per drone flight
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
                    fly_to_target = last_point or point
                    fly_to_dist, current_alt = generate_fly_to(
                        drone_waypoints,
                        car_waypoint,
                        fly_to_target,
                        drone,
                        hole_polygons,
                        avoidance_config=avoidance_config,
                        current_alt=current_alt,
                    )
                    total_drone_distance += fly_to_dist
                    if last_point is None and drone_waypoints:
                        last_wp = drone_waypoints[-1]
                        if abs(last_wp["lon"] - point[0]) < 1e-10 and abs(last_wp["lat"] - point[1]) < 1e-10:
                            # fly-to already added `point` (via hole-crossing 3D path)
                            last_point = point
                            if calc_vincenty(point, next_car_waypoint, lon_first=True) > (
                                drone.max_distance_no_load - total_drone_distance
                            ):
                                break
                            continue

                # If there's an untraversed point from previous drone - traverse it
                if last_point and first_run and path_crosses_holes(last_point, point, hole_polygons):
                    if use_3d:
                        path_3d, current_alt = avoid_obstacle_3d(
                            last_point, point, hole_polygons, avoidance_config, current_alt
                        )
                        total_drone_distance += add_3d_path(drone_waypoints, path_3d, drone)
                    else:
                        adjusted_path = adjust_path_around_holes(last_point, point, hole_polygons)
                        total_drone_distance += add_adjusted_path(
                            drone_waypoints, adjusted_path, drone, height=current_alt
                        )
                    last_point = point
                    first_run = False
                    continue

                if last_point and path_crosses_holes(last_point, point, hole_polygons):
                    if use_3d:
                        path_3d, current_alt = avoid_obstacle_3d(
                            last_point, point, hole_polygons, avoidance_config, current_alt
                        )
                        total_drone_distance += add_3d_path(drone_waypoints, path_3d, drone)
                    else:
                        adjusted_path = adjust_path_around_holes(last_point, point, hole_polygons)
                        total_drone_distance += add_adjusted_path(
                            drone_waypoints, adjusted_path, drone, height=current_alt
                        )
                    last_point = point
                    continue

                # Normal waypoint addition
                total_drone_distance += calc_vincenty(last_point or drone_waypoints[-1], point, lon_first=True)
                add_waypoint(drone_waypoints, point, drone, height=current_alt, spray_on=True)
                last_point = point

                # If you will not be able to return - break
                if calc_vincenty(point, next_car_waypoint, lon_first=True) > (
                    drone.max_distance_no_load - total_drone_distance
                ):
                    break

            if drone_waypoints:
                total_drone_distance += generate_fly_back(
                    drone_waypoints,
                    next_car_waypoint,
                    drone,
                    hole_polygons,
                    avoidance_config=avoidance_config,
                    current_alt=current_alt,
                )
                waypoints.append(drone_waypoints)
            if point is None:
                break
        if point is None:
            break
    waypoints = list(filter(lambda x: len(x) > 3, waypoints))
    return waypoints


def generate_fly_to(
    drone_waypoints, drones_init, coord_to, drone, hole_polygons=None, avoidance_config=None, current_alt=10
):
    """Generate fly-to waypoints. Returns (distance, exit_altitude)."""
    use_3d = avoidance_config is not None and avoidance_config.get("strategy", "2d") != "2d"
    if hole_polygons and path_crosses_holes(drones_init, coord_to, hole_polygons):
        if use_3d:
            path_3d, exit_alt = avoid_obstacle_3d(drones_init, coord_to, hole_polygons, avoidance_config, current_alt)
            return add_3d_path(drone_waypoints, path_3d, drone), exit_alt
        adjusted_path = adjust_path_around_holes(drones_init, coord_to, hole_polygons)
        return add_adjusted_path(drone_waypoints, adjusted_path, drone, height=current_alt), current_alt
    add_waypoint(drone_waypoints, drones_init, drone, height=current_alt)
    return calc_vincenty(drones_init, coord_to, lon_first=True), current_alt


def generate_fly_back(drone_waypoints, drones_init, drone, hole_polygons=None, avoidance_config=None, current_alt=10):
    use_3d = avoidance_config is not None and avoidance_config.get("strategy", "2d") != "2d"
    if hole_polygons and drone_waypoints:
        start_point = [drone_waypoints[-1]["lon"], drone_waypoints[-1]["lat"]]
        if path_crosses_holes(start_point, drones_init, hole_polygons):
            if use_3d:
                path_3d, _ = avoid_obstacle_3d(start_point, drones_init, hole_polygons, avoidance_config, current_alt)
                return add_3d_path(drone_waypoints, path_3d, drone)
            adjusted_path = adjust_path_around_holes(start_point, drones_init, hole_polygons)
            return add_adjusted_path(drone_waypoints, adjusted_path, drone, height=current_alt)
    add_waypoint(drone_waypoints, drones_init, drone, height=current_alt)
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


def add_adjusted_path(drone_waypoints, adjusted_path, drone, height=10):
    total_distance = 0
    for idx, point in enumerate(adjusted_path):
        if idx > 0:
            total_distance += calc_vincenty(adjusted_path[idx - 1], point, lon_first=True)
        # Skip first point if it duplicates the last waypoint already added
        if idx == 0 and drone_waypoints:
            last = drone_waypoints[-1]
            if abs(last["lon"] - point[0]) < 1e-10 and abs(last["lat"] - point[1]) < 1e-10:
                continue
        spray_on = idx == len(adjusted_path) - 1
        add_waypoint(drone_waypoints, point, drone, height=height, spray_on=spray_on)
    return total_distance
