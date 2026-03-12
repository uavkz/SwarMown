"""
Tests for mainapp.service_routing: get_route, iterate_zamboni,
path_crosses_holes, adjust_path_around_holes.
"""

from copy import deepcopy

from django.test import TestCase
from pyproj import Transformer
from shapely.geometry import Polygon as ShapelyPolygon

from mainapp.models import Drone
from mainapp.service_routing import (
    adjust_path_around_holes,
    get_route,
    iterate_zamboni,
    path_crosses_holes,
)

# A small rectangular field (lon, lat format)
RECT_FIELD = [[30.0, 50.0], [30.1, 50.0], [30.1, 50.05], [30.0, 50.05]]
ROAD = [[30.0, 49.99], [30.1, 49.99]]

# Transformer matching the project's equidistant projection
PYPROJ_TRANSFORMER = Transformer.from_crs("epsg:4087", "epsg:4326", always_xy=True)

GRID_STEP = 500


def _make_drone():
    """Create and save a Drone instance for testing."""
    drone = Drone(
        name="Test",
        model="T1",
        max_speed=15,
        max_distance_no_load=10,
        weight=5,
        max_load=2,
        slowdown_ratio_per_degree=0.005,
        min_slowdown_ratio=0.01,
        price_per_cycle=3,
        price_per_kilometer=0.1,
        price_per_hour=0.01,
    )
    drone.save()
    return drone


# ---------------------------------------------------------------------------
# get_route tests
# ---------------------------------------------------------------------------
class GetRouteSmokeTest(TestCase):
    """Smoke test: get_route with no holes returns the expected 4-tuple."""

    def setUp(self):
        self.drone = _make_drone()

    def test_returns_four_tuple(self):
        grid, waypoints, car_waypoints, initial = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=GRID_STEP,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
        )
        self.assertIsInstance(grid, list)
        self.assertIsInstance(waypoints, list)
        self.assertIsInstance(car_waypoints, list)
        self.assertIsNotNone(initial)


class GetRouteReturnsGridWithPointsTest(TestCase):
    """get_route returns a non-empty grid (list of lists with points)."""

    def setUp(self):
        self.drone = _make_drone()

    def test_grid_non_empty(self):
        grid, _, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=GRID_STEP,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
        )
        non_empty = [line for line in grid if line]
        self.assertGreater(len(non_empty), 0, "Grid should have non-empty lines")


class GetRouteReturnsWaypointsTest(TestCase):
    """Waypoints are lists of drone flight segments with expected keys."""

    def setUp(self):
        self.drone = _make_drone()

    def test_waypoints_structure(self):
        _, waypoints, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=GRID_STEP,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
        )
        self.assertIsInstance(waypoints, list)
        # Each segment is a list of waypoint dicts
        for segment in waypoints:
            self.assertIsInstance(segment, list)
            for wp in segment:
                self.assertIn("lat", wp)
                self.assertIn("lon", wp)
                self.assertIn("drone", wp)
                self.assertIn("spray_on", wp)


class GetRouteDirectionAffectsGridTest(TestCase):
    """direction=0 and direction=90 produce different grids."""

    def setUp(self):
        self.drone = _make_drone()

    def test_direction_differs(self):
        grid_0, _, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=GRID_STEP,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
        )
        grid_90, _, _, _ = get_route(
            car_move=[0.5],
            direction=90,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=GRID_STEP,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
        )
        flat_0 = [pt for line in grid_0 for pt in line]
        flat_90 = [pt for line in grid_90 for pt in line]
        self.assertNotEqual(flat_0, flat_90, "Different directions should produce different grids")


class GetRouteStartCornerAffectsTraversalTest(TestCase):
    """start='ne' vs start='sw' produce different first waypoints."""

    def setUp(self):
        self.drone = _make_drone()

    def test_start_corner_differs(self):
        _, wps_ne, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=GRID_STEP,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
        )
        _, wps_sw, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="sw",
            field=deepcopy(RECT_FIELD),
            grid_step=GRID_STEP,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
        )

        # Compare the first spray-on waypoint in the first segment
        def first_spray_point(waypoints):
            for segment in waypoints:
                for wp in segment:
                    if wp.get("spray_on"):
                        return (wp["lat"], wp["lon"])
            return None

        pt_ne = first_spray_point(wps_ne)
        pt_sw = first_spray_point(wps_sw)
        self.assertIsNotNone(pt_ne)
        self.assertIsNotNone(pt_sw)
        self.assertNotEqual(pt_ne, pt_sw, "Different start corners should yield different first spray points")


class GetRouteGridCoverageTest(TestCase):
    """Total spray_on waypoints roughly correspond to total grid points."""

    def setUp(self):
        self.drone = _make_drone()

    def test_coverage(self):
        grid, waypoints, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=GRID_STEP,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
        )
        total_grid_pts = sum(len(line) for line in grid)
        spray_on_count = sum(1 for seg in waypoints for wp in seg if wp.get("spray_on"))
        # spray_on waypoints should be at least 50% of grid points (allowing
        # for some being skipped due to drone distance limits)
        self.assertGreater(
            spray_on_count,
            total_grid_pts * 0.5,
            f"spray_on count ({spray_on_count}) is too low vs grid ({total_grid_pts})",
        )


# ---------------------------------------------------------------------------
# iterate_zamboni tests
# ---------------------------------------------------------------------------
class IterateZamboniReturnsAllPointsTest(TestCase):
    """For a 3x3 grid, zamboni yields 9 points."""

    def test_yields_all_points(self):
        grid = [
            [[0, 0], [0, 1], [0, 2]],
            [[1, 0], [1, 1], [1, 2]],
            [[2, 0], [2, 1], [2, 2]],
        ]
        points = list(iterate_zamboni(grid, start="sw"))
        self.assertEqual(len(points), 9, "3x3 grid should yield 9 points")


class IterateZamboniAlternatesDirectionTest(TestCase):
    """With start='sw', rows alternate direction in a boustrophedon pattern."""

    def test_alternating_direction(self):
        grid = [
            [[0, 0], [0, 1], [0, 2]],
            [[1, 0], [1, 1], [1, 2]],
            [[2, 0], [2, 1], [2, 2]],
        ]
        points = list(iterate_zamboni(grid, start="sw"))

        # start="sw":
        #   s -> grid NOT reversed (rows in natural order 0,1,2)
        #   w -> condition is (line_n % 2 == 0) triggers reverse
        # Row 0 (line_n=0): reversed -> [0,2], [0,1], [0,0]
        self.assertEqual(points[0], [0, 2])
        self.assertEqual(points[1], [0, 1])
        self.assertEqual(points[2], [0, 0])

        # Row 1 (line_n=1): NOT reversed -> [1,0], [1,1], [1,2]
        self.assertEqual(points[3], [1, 0])
        self.assertEqual(points[4], [1, 1])
        self.assertEqual(points[5], [1, 2])


# ---------------------------------------------------------------------------
# path_crosses_holes tests
# ---------------------------------------------------------------------------
class PathCrossesHolesNoHolesTest(TestCase):
    """No holes means path never crosses anything."""

    def test_no_holes_returns_false(self):
        result = path_crosses_holes([30.0, 50.0], [30.1, 50.0], [])
        self.assertFalse(result)


class PathCrossesHolesThroughHoleTest(TestCase):
    """A line that passes through a hole returns True."""

    def test_path_through_hole(self):
        hole = ShapelyPolygon(
            [
                (30.04, 50.02),
                (30.06, 50.02),
                (30.06, 50.03),
                (30.04, 50.03),
            ]
        )
        result = path_crosses_holes([30.0, 50.025], [30.1, 50.025], [hole])
        self.assertTrue(result, "Path through the hole should be detected")


class PathCrossesHolesAroundHoleTest(TestCase):
    """A line that misses the hole returns False."""

    def test_path_around_hole(self):
        hole = ShapelyPolygon(
            [
                (30.04, 50.02),
                (30.06, 50.02),
                (30.06, 50.03),
                (30.04, 50.03),
            ]
        )
        # Path goes well below the hole
        result = path_crosses_holes([30.0, 50.0], [30.1, 50.0], [hole])
        self.assertFalse(result, "Path below hole should not cross it")


# ---------------------------------------------------------------------------
# adjust_path_around_holes tests
# ---------------------------------------------------------------------------
class AdjustPathAroundHolesDetourAddsPointsTest(TestCase):
    """Adjusted path has more points than the direct [start, end]."""

    def test_detour_adds_points(self):
        hole = ShapelyPolygon(
            [
                (30.04, 50.02),
                (30.06, 50.02),
                (30.06, 50.03),
                (30.04, 50.03),
            ]
        )
        start_pt = [30.0, 50.025]
        end_pt = [30.1, 50.025]

        adjusted = adjust_path_around_holes(start_pt, end_pt, [hole])
        self.assertGreater(
            len(adjusted),
            2,
            "Detour around hole should produce more than 2 points",
        )
        # First and last points should match start/end
        self.assertEqual(adjusted[0], start_pt)
        self.assertEqual(adjusted[-1], end_pt)


class AdjustPathAroundHolesAvoidsHoleTest(TestCase):
    """No segment of the adjusted path crosses the hole."""

    def test_adjusted_avoids_hole(self):
        hole = ShapelyPolygon(
            [
                (30.04, 50.02),
                (30.06, 50.02),
                (30.06, 50.03),
                (30.04, 50.03),
            ]
        )
        start_pt = [30.0, 50.025]
        end_pt = [30.1, 50.025]

        adjusted = adjust_path_around_holes(start_pt, end_pt, [hole])

        for i in range(len(adjusted) - 1):
            crosses = path_crosses_holes(adjusted[i], adjusted[i + 1], [hole])
            self.assertFalse(
                crosses,
                f"Segment {i}->{i + 1} of adjusted path should not cross the hole: {adjusted[i]} -> {adjusted[i + 1]}",
            )
