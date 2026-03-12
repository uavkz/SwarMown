"""
Tests for mainapp.services_draw: get_grid, get_car_waypoints, get_car_waypoints_by_ratio_list.
"""

from copy import deepcopy

from django.test import TestCase
from pyproj import Transformer
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry.polygon import Polygon as ShapelyPolygon

from mainapp.services_draw import (
    get_car_waypoints,
    get_car_waypoints_by_ratio_list,
    get_grid,
)

# A small rectangular field (lon, lat format)
RECT_FIELD = [[30.0, 50.0], [30.1, 50.0], [30.1, 50.05], [30.0, 50.05]]
ROAD = [[30.0, 49.99], [30.1, 49.99]]

# Transformer matching the one used internally by the project (epsg:4087 -> epsg:4326)
TRANSFORMER = Transformer.from_crs("epsg:4087", "epsg:4326", always_xy=True)

# Grid step in meters (equidistant projection units)
DEFAULT_STEP = 500


def _flat_points(grid):
    """Flatten a grid (list of lines) into a single list of [lon, lat] points."""
    return [pt for line in grid for pt in line]


class GetGridSmokeTest(TestCase):
    """get_grid returns a non-empty list of lines, each line containing points."""

    def test_returns_non_empty_grid(self):
        grid = get_grid(deepcopy(RECT_FIELD), DEFAULT_STEP, angle=0, trans=TRANSFORMER)
        non_empty_lines = [line for line in grid if line]
        self.assertGreater(len(non_empty_lines), 0, "Grid must have at least one non-empty line")
        for line in non_empty_lines:
            self.assertGreater(len(line), 0)
            for point in line:
                self.assertEqual(len(point), 2, "Each point must be [lon, lat]")


class GetGridAngleTest(TestCase):
    """Different orientations (angle=0 vs angle=90) produce different grids."""

    def test_angle_0_vs_90_differ(self):
        grid_0 = get_grid(deepcopy(RECT_FIELD), DEFAULT_STEP, angle=0, trans=TRANSFORMER)
        grid_90 = get_grid(deepcopy(RECT_FIELD), DEFAULT_STEP, angle=90, trans=TRANSFORMER)

        pts_0 = _flat_points(grid_0)
        pts_90 = _flat_points(grid_90)

        # Both grids should be non-empty
        self.assertGreater(len(pts_0), 0)
        self.assertGreater(len(pts_90), 0)

        # The two grids must not be identical (point sets differ)
        self.assertNotEqual(pts_0, pts_90, "Grids at angle 0 and 90 should differ")


class GetGridPointsInsideFieldTest(TestCase):
    """All generated grid points lie inside (or very close to) the field polygon."""

    def test_points_inside_field(self):
        grid = get_grid(deepcopy(RECT_FIELD), DEFAULT_STEP, angle=0, trans=TRANSFORMER)
        pts = _flat_points(grid)
        self.assertGreater(len(pts), 0, "Grid must not be empty for this test")

        # Build the field polygon with a small buffer to allow floating-point tolerance
        field_poly = ShapelyPolygon(RECT_FIELD)
        buffer_deg = 0.005  # ~500 m tolerance in degrees
        buffered = field_poly.buffer(buffer_deg)

        for pt in pts:
            self.assertTrue(
                buffered.contains(ShapelyPoint(pt[0], pt[1])),
                f"Point {pt} is outside the (buffered) field polygon",
            )


class GetGridStepSizeTest(TestCase):
    """A smaller step produces more grid points than a larger step."""

    def test_smaller_step_more_points(self):
        grid_large = get_grid(deepcopy(RECT_FIELD), 1000, angle=0, trans=TRANSFORMER)
        grid_small = get_grid(deepcopy(RECT_FIELD), 300, angle=0, trans=TRANSFORMER)

        pts_large = _flat_points(grid_large)
        pts_small = _flat_points(grid_small)

        self.assertGreater(
            len(pts_small),
            len(pts_large),
            "Smaller step should produce more grid points",
        )


class GetCarWaypointsTest(TestCase):
    """get_car_waypoints with how='no' returns 3 waypoints: start, middle, end."""

    def test_no_mode_returns_three_waypoints(self):
        # get_car_waypoints needs a grid argument but with how="no" it is not used
        grid = get_grid(deepcopy(RECT_FIELD), DEFAULT_STEP, angle=0, trans=TRANSFORMER)
        car_wps = get_car_waypoints(grid, deepcopy(ROAD), how="no")

        self.assertEqual(len(car_wps), 3, "how='no' should produce exactly 3 car waypoints")

        # First waypoint should be the start of the road
        self.assertAlmostEqual(car_wps[0][0], ROAD[0][0], places=5)
        self.assertAlmostEqual(car_wps[0][1], ROAD[0][1], places=5)

        # Last waypoint should be the end of the road
        self.assertAlmostEqual(car_wps[2][0], ROAD[-1][0], places=5)
        self.assertAlmostEqual(car_wps[2][1], ROAD[-1][1], places=5)


class GetCarWaypointsByRatioListTest(TestCase):
    """get_car_waypoints_by_ratio_list produces correct waypoints for given ratios."""

    def test_ratio_0_gives_start(self):
        wps = get_car_waypoints_by_ratio_list(deepcopy(ROAD), [0.0])
        self.assertEqual(len(wps), 1)
        self.assertAlmostEqual(wps[0][0], ROAD[0][0], places=5)
        self.assertAlmostEqual(wps[0][1], ROAD[0][1], places=5)

    def test_ratio_1_gives_end(self):
        wps = get_car_waypoints_by_ratio_list(deepcopy(ROAD), [1.0])
        self.assertEqual(len(wps), 1)
        self.assertAlmostEqual(wps[0][0], ROAD[-1][0], places=5)
        self.assertAlmostEqual(wps[0][1], ROAD[-1][1], places=5)

    def test_ratio_half_gives_middle(self):
        wps = get_car_waypoints_by_ratio_list(deepcopy(ROAD), [0.5])
        self.assertEqual(len(wps), 1)
        expected_mid_lon = (ROAD[0][0] + ROAD[-1][0]) / 2
        expected_mid_lat = (ROAD[0][1] + ROAD[-1][1]) / 2
        self.assertAlmostEqual(wps[0][0], expected_mid_lon, places=3)
        self.assertAlmostEqual(wps[0][1], expected_mid_lat, places=3)


class GetCarWaypointsByRatioListOrderingTest(TestCase):
    """Ratios [0.25, 0.75] return 2 points in order along the road."""

    def test_ordering(self):
        wps = get_car_waypoints_by_ratio_list(deepcopy(ROAD), [0.25, 0.75])
        self.assertEqual(len(wps), 2)

        # For a west-to-east road at constant latitude, longitude should increase
        self.assertLess(
            wps[0][0],
            wps[1][0],
            "Waypoint at ratio 0.25 should have smaller longitude than at 0.75",
        )

        # Both points should lie between start and end longitude
        self.assertGreater(wps[0][0], ROAD[0][0])
        self.assertLess(wps[1][0], ROAD[-1][0])
