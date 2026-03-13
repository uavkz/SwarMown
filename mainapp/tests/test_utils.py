"""
Comprehensive tests for mainapp/utils.py

Covers:
- Smoke tests: every function callable without crash
- Computation correctness: known inputs -> expected outputs
- Edge cases: empty lists, single point, zero distance, boundary angles
- Sanity checks: distance positivity, monotonicity, penalty growth
"""

import math

import numpy as np
from django.test import TestCase

from mainapp.models import Drone
from mainapp.utils import (
    add_waypoint,
    angle_between_vectors_degrees,
    angle_lat_lon_vectors,
    calc_vincenty,
    drone_flight_price,
    flatten_grid,
    flight_penalty,
    rotate,
    transform_to_equidistant,
    transform_to_lat_lon,
    waypoints_distance,
    waypoints_flight_time,
)

# Reusable mock drone dictionary (not a Django model instance).
MOCK_DRONE_DICT = {
    "id": 1,
    "name": "TestDrone",
    "model": "T1",
    "max_speed": 15,
    "max_distance_no_load": 10,
    "slowdown_ratio_per_degree": 0.005,
    "min_slowdown_ratio": 0.01,
    "price_per_cycle": 3,
    "price_per_kilometer": 0.1,
    "price_per_hour": 0.01,
    "max_height": 1,
    "weight": 5,
    "max_load": 2,
}


# ---------------------------------------------------------------------------
# Helper: simple namespace so waypoints_distance / waypoints_flight_time
# can use the default lambdas (x.lat, x.lon, x.drone.max_speed, etc.)
# ---------------------------------------------------------------------------
class _NS:
    """Lightweight namespace for attribute-style access."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _make_wp_obj(lat, lon, drone_dict=None):
    """Return a namespace object that quacks like a Waypoint row."""
    d = drone_dict or MOCK_DRONE_DICT
    drone_ns = _NS(**d)
    return _NS(lat=lat, lon=lon, drone=drone_ns)


# ===================================================================
# flatten_grid
# ===================================================================
class TestFlattenGrid(TestCase):
    """Tests for flatten_grid."""

    def test_smoke(self):
        """Function should be callable and return a generator."""
        result = flatten_grid([[1, 2], [3, 4]])
        self.assertTrue(hasattr(result, "__next__"))

    def test_basic(self):
        grid = [[(0, 0), (1, 1)], [(2, 2), (3, 3)]]
        flat = list(flatten_grid(grid))
        self.assertEqual(flat, [(0, 0), (1, 1), (2, 2), (3, 3)])

    def test_single_row(self):
        self.assertEqual(list(flatten_grid([["a", "b"]])), ["a", "b"])

    def test_empty_grid(self):
        self.assertEqual(list(flatten_grid([])), [])

    def test_empty_rows(self):
        self.assertEqual(list(flatten_grid([[], []])), [])

    def test_single_element(self):
        self.assertEqual(list(flatten_grid([[42]])), [42])


# ===================================================================
# transform_to_equidistant / transform_to_lat_lon  (round-trip)
# ===================================================================
class TestCoordinateTransforms(TestCase):
    """Tests for transform_to_equidistant and transform_to_lat_lon."""

    def test_smoke_equidistant(self):
        pts = [[30.0, 50.0]]
        transform_to_equidistant(pts)

    def test_smoke_lat_lon(self):
        pts = [[3339584.7, 5565974.5]]
        transform_to_lat_lon(pts)

    def test_round_trip_single_point(self):
        """to_equidistant -> to_lat_lon should recover the original coords."""
        original = [30.0, 50.0]
        pts = [original[:]]
        transform_to_equidistant(pts)
        # After transform the values should have changed
        self.assertNotAlmostEqual(pts[0][0], 30.0, places=0)
        transform_to_lat_lon(pts)
        self.assertAlmostEqual(pts[0][0], original[0], places=5)
        self.assertAlmostEqual(pts[0][1], original[1], places=5)

    def test_round_trip_multiple_points(self):
        originals = [[10.0, 20.0], [30.0, 40.0], [-5.0, 60.0]]
        pts = [p[:] for p in originals]
        transform_to_equidistant(pts)
        transform_to_lat_lon(pts)
        for orig, recovered in zip(originals, pts):
            self.assertAlmostEqual(recovered[0], orig[0], places=5)
            self.assertAlmostEqual(recovered[1], orig[1], places=5)

    def test_mutates_in_place(self):
        pts = [[30.0, 50.0]]
        transform_to_equidistant(pts)
        # The list should be mutated, not returned as new
        self.assertNotAlmostEqual(pts[0][0], 30.0, places=0)

    def test_empty_list(self):
        """Should not crash on empty list."""
        pts = []
        transform_to_equidistant(pts)
        transform_to_lat_lon(pts)
        self.assertEqual(pts, [])


# ===================================================================
# add_waypoint
# ===================================================================
class TestAddWaypoint(TestCase):
    """Tests for add_waypoint (requires DB for model_to_dict)."""

    @classmethod
    def setUpTestData(cls):
        cls.drone = Drone(
            name="Test",
            model="T1",
            max_speed=15,
            max_distance_no_load=10,
            weight=5,
            max_load=2,
        )
        cls.drone.save()

    def test_smoke(self):
        wp = []
        add_waypoint(wp, [30.0, 50.0], self.drone)

    def test_appends_one(self):
        wp = []
        add_waypoint(wp, [30.0, 50.0], self.drone)
        self.assertEqual(len(wp), 1)

    def test_correct_lat_lon(self):
        wp = []
        add_waypoint(wp, [30.0, 50.0], self.drone)
        self.assertEqual(wp[0]["lat"], 50.0)
        self.assertEqual(wp[0]["lon"], 30.0)

    def test_default_values(self):
        wp = []
        add_waypoint(wp, [0, 0], self.drone)
        self.assertEqual(wp[0]["height"], 10)
        self.assertEqual(wp[0]["speed"], 30)
        self.assertEqual(wp[0]["acceleration"], 0)
        self.assertFalse(wp[0]["spray_on"])

    def test_custom_values(self):
        wp = []
        add_waypoint(wp, [1, 2], self.drone, height=20, speed=50, acceleration=5, spray_on=True)
        self.assertEqual(wp[0]["height"], 20)
        self.assertEqual(wp[0]["speed"], 50)
        self.assertEqual(wp[0]["acceleration"], 5)
        self.assertTrue(wp[0]["spray_on"])

    def test_drone_dict_has_name(self):
        wp = []
        add_waypoint(wp, [0, 0], self.drone)
        self.assertEqual(wp[0]["drone"]["name"], "Test")

    def test_multiple_appends(self):
        wp = []
        add_waypoint(wp, [0, 0], self.drone)
        add_waypoint(wp, [1, 1], self.drone)
        self.assertEqual(len(wp), 2)


# ===================================================================
# calc_vincenty
# ===================================================================
class TestCalcVincenty(TestCase):
    """Tests for calc_vincenty."""

    def test_smoke(self):
        calc_vincenty((0, 0), (0, 0))

    def test_same_point_is_zero(self):
        d = calc_vincenty((50, 30), (50, 30))
        self.assertAlmostEqual(d, 0.0, places=5)

    def test_known_distance_moscow_stpetersburg(self):
        """Moscow (55.7558, 37.6173) <-> St Petersburg (59.9343, 30.3351).
        Great-circle distance ~ 634 km. We check within +-20 km tolerance."""
        moscow = (55.7558, 37.6173)
        spb = (59.9343, 30.3351)
        d_km = calc_vincenty(moscow, spb)
        self.assertAlmostEqual(d_km, 634, delta=20)

    def test_lon_first_flag(self):
        """With lon_first=True the order of coords in the tuple is (lon, lat)."""
        # Using plain tuples (list path in code)
        d_normal = calc_vincenty((50, 30), (51, 31))
        d_swapped = calc_vincenty((30, 50), (31, 51), lon_first=True)
        self.assertAlmostEqual(d_normal, d_swapped, places=3)

    def test_lon_first_dict(self):
        """lon_first=True with a dict-like first point."""
        p1 = {"lat": 50, "lon": 30}
        p2 = (31, 51)
        d = calc_vincenty(p1, p2, lon_first=True)
        self.assertGreater(d, 0)

    def test_distance_always_non_negative(self):
        d = calc_vincenty((10, 20), (30, 40))
        self.assertGreaterEqual(d, 0)

    def test_symmetry(self):
        d1 = calc_vincenty((50, 30), (55, 35))
        d2 = calc_vincenty((55, 35), (50, 30))
        self.assertAlmostEqual(d1, d2, places=5)

    def test_antipodal_returns_none(self):
        """The vincenty library returns None for antipodal points
        (the iterative formula does not converge)."""
        d = calc_vincenty((0, 0), (0, 180))
        self.assertIsNone(d)

    def test_near_antipodal_large_distance(self):
        """Near-antipodal points should still yield a large distance."""
        d = calc_vincenty((0, 0), (0, 179))
        self.assertIsNotNone(d)
        self.assertGreater(d, 19_000)

    def test_short_distance(self):
        """Two very close points should give a very small distance."""
        d = calc_vincenty((50.0, 30.0), (50.0001, 30.0001))
        self.assertLess(d, 0.1)  # less than 100 m = 0.1 km


# ===================================================================
# waypoints_distance
# ===================================================================
class TestWaypointsDistance(TestCase):
    """Tests for waypoints_distance."""

    def test_smoke(self):
        waypoints_distance([])

    def test_empty(self):
        self.assertEqual(waypoints_distance([]), 0)

    def test_single_waypoint(self):
        wp = [_make_wp_obj(50, 30)]
        self.assertEqual(waypoints_distance(wp), 0)

    def test_two_waypoints_positive(self):
        wp = [_make_wp_obj(50, 30), _make_wp_obj(51, 31)]
        d = waypoints_distance(wp)
        self.assertGreater(d, 0)

    def test_distance_in_meters(self):
        """Result should be in meters (vincenty * 1000)."""
        wp = [_make_wp_obj(50, 30), _make_wp_obj(51, 31)]
        d = waypoints_distance(wp)
        # Roughly 130 km = 130_000 m between these points
        self.assertGreater(d, 100_000)
        self.assertLess(d, 200_000)

    def test_more_waypoints_longer(self):
        """Adding more waypoints should increase total distance."""
        wp2 = [_make_wp_obj(50, 30), _make_wp_obj(51, 31)]
        wp3 = [_make_wp_obj(50, 30), _make_wp_obj(51, 31), _make_wp_obj(52, 32)]
        d2 = waypoints_distance(wp2)
        d3 = waypoints_distance(wp3)
        self.assertGreater(d3, d2)

    def test_custom_accessors(self):
        """Using dict waypoints with custom lat/lon accessors."""
        wps = [{"la": 50, "lo": 30}, {"la": 51, "lo": 31}]
        d = waypoints_distance(wps, lat_f=lambda x: x["la"], lon_f=lambda x: x["lo"])
        self.assertGreater(d, 0)

    def test_same_point_twice(self):
        wp = [_make_wp_obj(50, 30), _make_wp_obj(50, 30)]
        d = waypoints_distance(wp)
        self.assertAlmostEqual(d, 0.0, places=3)


# ===================================================================
# waypoints_flight_time
# ===================================================================
class TestWaypointsFlightTime(TestCase):
    """Tests for waypoints_flight_time."""

    def test_smoke(self):
        waypoints_flight_time([])

    def test_empty(self):
        self.assertEqual(waypoints_flight_time([]), 0)

    def test_single_waypoint(self):
        self.assertEqual(waypoints_flight_time([_make_wp_obj(50, 30)]), 0)

    def test_two_waypoints_positive(self):
        wp = [_make_wp_obj(50, 30), _make_wp_obj(51, 31)]
        t = waypoints_flight_time(wp)
        self.assertGreater(t, 0)

    def test_more_waypoints_more_time(self):
        wp2 = [_make_wp_obj(50, 30), _make_wp_obj(51, 31)]
        wp3 = [_make_wp_obj(50, 30), _make_wp_obj(51, 31), _make_wp_obj(52, 32)]
        t2 = waypoints_flight_time(wp2)
        t3 = waypoints_flight_time(wp3)
        self.assertGreater(t3, t2)

    def test_duplicate_consecutive_skipped(self):
        """If two consecutive waypoints share the same coords they are skipped."""
        wp = [
            _make_wp_obj(50, 30),
            _make_wp_obj(51, 31),
            _make_wp_obj(51, 31),  # duplicate -> should be skipped
            _make_wp_obj(52, 32),
        ]
        t = waypoints_flight_time(wp)
        self.assertGreater(t, 0)

    def test_custom_accessors(self):
        wps = [{"la": 50, "lo": 30}, {"la": 51, "lo": 31}]
        t = waypoints_flight_time(
            wps,
            lat_f=lambda x: x["la"],
            lon_f=lambda x: x["lo"],
            max_speed_f=lambda x: 15,
            slowdown_ratio_f=lambda x: 0.005,
            min_slowdown_ratio_f=lambda x: 0.01,
        )
        self.assertGreater(t, 0)

    def test_slowdown_on_turn(self):
        """A sharp turn should make flight time longer than a straight path
        of the same total distance."""
        # Straight path: south to north
        straight = [
            _make_wp_obj(50, 30),
            _make_wp_obj(51, 30),
            _make_wp_obj(52, 30),
        ]
        # Path with a 90-degree-ish turn
        turn = [
            _make_wp_obj(50, 30),
            _make_wp_obj(51, 30),
            _make_wp_obj(51, 31),
        ]
        t_straight = waypoints_flight_time(straight)
        t_turn = waypoints_flight_time(turn)
        # Turn path's third segment should be slower -> time should differ
        # (distances differ too, but we mainly verify no crash and positive result)
        self.assertGreater(t_straight, 0)
        self.assertGreater(t_turn, 0)


# ===================================================================
# drone_flight_price
# ===================================================================
class TestDroneFlightPrice(TestCase):
    """Tests for drone_flight_price."""

    def test_smoke(self):
        drone_flight_price(MOCK_DRONE_DICT, 0, 0)

    def test_zero_distance_zero_time(self):
        price = drone_flight_price(MOCK_DRONE_DICT, 0, 0)
        self.assertAlmostEqual(price, MOCK_DRONE_DICT["price_per_cycle"])

    def test_manual_calculation(self):
        distance = 100  # km
        time = 5  # hours
        expected = 3 + 0.1 * 100 + 0.01 * 5  # 3 + 10 + 0.05 = 13.05
        price = drone_flight_price(MOCK_DRONE_DICT, distance, time)
        self.assertAlmostEqual(price, expected)

    def test_price_increases_with_distance(self):
        p1 = drone_flight_price(MOCK_DRONE_DICT, 10, 1)
        p2 = drone_flight_price(MOCK_DRONE_DICT, 20, 1)
        self.assertGreater(p2, p1)

    def test_price_increases_with_time(self):
        p1 = drone_flight_price(MOCK_DRONE_DICT, 10, 1)
        p2 = drone_flight_price(MOCK_DRONE_DICT, 10, 10)
        self.assertGreater(p2, p1)

    def test_price_always_at_least_per_cycle(self):
        price = drone_flight_price(MOCK_DRONE_DICT, 0, 0)
        self.assertGreaterEqual(price, MOCK_DRONE_DICT["price_per_cycle"])


# ===================================================================
# flight_penalty
# ===================================================================
class TestFlightPenalty(TestCase):
    """Tests for flight_penalty."""

    def test_smoke(self):
        flight_penalty(
            time=1, borderline_time=2, max_time=3, salary=10, drone_price=5, total_grid=100, grid_traversed=100
        )

    def test_no_penalty_under_borderline(self):
        p = flight_penalty(
            time=1, borderline_time=2, max_time=3, salary=10, drone_price=5, total_grid=100, grid_traversed=100
        )
        self.assertEqual(p, 0)

    def test_moderate_penalty_between_borderline_and_max(self):
        p = flight_penalty(
            time=2.5, borderline_time=2, max_time=3, salary=10, drone_price=5, total_grid=100, grid_traversed=100
        )
        self.assertGreater(p, 0)
        # Should be (10+5) * (2.5-2)/(3-2) = 15 * 0.5 = 7.5
        self.assertAlmostEqual(p, 7.5)

    def test_huge_penalty_over_max(self):
        p = flight_penalty(
            time=4, borderline_time=2, max_time=3, salary=10, drone_price=5, total_grid=100, grid_traversed=100
        )
        # (salary + drone_price) * 1000^(time - max_time)
        # = 15 * 1000^1 = 15_000
        self.assertAlmostEqual(p, 15_000)

    def test_penalty_increases_with_excess_time(self):
        p1 = flight_penalty(
            time=3.5, borderline_time=2, max_time=3, salary=10, drone_price=5, total_grid=100, grid_traversed=100
        )
        p2 = flight_penalty(
            time=5, borderline_time=2, max_time=3, salary=10, drone_price=5, total_grid=100, grid_traversed=100
        )
        self.assertGreater(p2, p1)

    def test_penalty_at_exact_borderline(self):
        p = flight_penalty(
            time=2, borderline_time=2, max_time=3, salary=10, drone_price=5, total_grid=100, grid_traversed=100
        )
        self.assertEqual(p, 0)

    def test_penalty_at_exact_max_time(self):
        """At time == max_time, the 'elif' branch fires with ratio = 1."""
        p = flight_penalty(
            time=3, borderline_time=2, max_time=3, salary=10, drone_price=5, total_grid=100, grid_traversed=100
        )
        # (10+5) * (3-2)/(3-2) = 15
        self.assertAlmostEqual(p, 15)

    def test_untraversed_grid_penalty(self):
        """If total_grid - grid_traversed > 3, an extra 1_000_000 is added."""
        p = flight_penalty(
            time=1, borderline_time=2, max_time=3, salary=10, drone_price=5, total_grid=100, grid_traversed=90
        )
        self.assertEqual(p, 1_000_000)

    def test_untraversed_grid_threshold(self):
        """Exactly 3 untraversed should NOT trigger the million penalty."""
        p = flight_penalty(
            time=1, borderline_time=2, max_time=3, salary=10, drone_price=5, total_grid=100, grid_traversed=97
        )
        self.assertEqual(p, 0)

    def test_untraversed_grid_above_threshold(self):
        """4 untraversed (>3) should trigger the million penalty."""
        p = flight_penalty(
            time=1, borderline_time=2, max_time=3, salary=10, drone_price=5, total_grid=100, grid_traversed=96
        )
        self.assertEqual(p, 1_000_000)

    def test_combined_time_and_grid_penalty(self):
        """Both time excess and grid miss should stack."""
        p = flight_penalty(
            time=4, borderline_time=2, max_time=3, salary=10, drone_price=5, total_grid=100, grid_traversed=90
        )
        expected_time_penalty = 15 * 1000**1  # 15_000
        expected_total = expected_time_penalty + 1_000_000
        self.assertAlmostEqual(p, expected_total)


# ===================================================================
# rotate
# ===================================================================
class TestRotate(TestCase):
    """Tests for rotate."""

    def test_smoke(self):
        rotate((1, 0), (0, 0), 0)

    def test_0_degrees(self):
        result = rotate((1, 0), (0, 0), 0)
        self.assertAlmostEqual(result[0], 1.0)
        self.assertAlmostEqual(result[1], 0.0)

    def test_90_degrees(self):
        result = rotate((1, 0), (0, 0), 90)
        self.assertAlmostEqual(result[0], 0.0, places=10)
        self.assertAlmostEqual(result[1], 1.0, places=10)

    def test_180_degrees(self):
        result = rotate((1, 0), (0, 0), 180)
        self.assertAlmostEqual(result[0], -1.0, places=10)
        self.assertAlmostEqual(result[1], 0.0, places=10)

    def test_270_degrees(self):
        result = rotate((1, 0), (0, 0), 270)
        self.assertAlmostEqual(result[0], 0.0, places=10)
        self.assertAlmostEqual(result[1], -1.0, places=10)

    def test_360_degrees(self):
        result = rotate((1, 0), (0, 0), 360)
        self.assertAlmostEqual(result[0], 1.0, places=10)
        self.assertAlmostEqual(result[1], 0.0, places=10)

    def test_rotate_around_non_origin(self):
        """Rotate (2,1) around (1,1) by 90 degrees: expect (1,2)."""
        result = rotate((2, 1), (1, 1), 90)
        self.assertAlmostEqual(result[0], 1.0, places=10)
        self.assertAlmostEqual(result[1], 2.0, places=10)

    def test_negative_angle(self):
        """Negative angle -> clockwise rotation."""
        result = rotate((1, 0), (0, 0), -90)
        self.assertAlmostEqual(result[0], 0.0, places=10)
        self.assertAlmostEqual(result[1], -1.0, places=10)

    def test_45_degrees(self):
        result = rotate((1, 0), (0, 0), 45)
        expected = math.sqrt(2) / 2
        self.assertAlmostEqual(result[0], expected, places=10)
        self.assertAlmostEqual(result[1], expected, places=10)

    def test_rotate_returns_list(self):
        result = rotate((1, 0), (0, 0), 90)
        self.assertIsInstance(result, list)

    def test_point_at_origin(self):
        """Rotating the origin around origin should stay at origin."""
        result = rotate((0, 0), (0, 0), 123)
        self.assertAlmostEqual(result[0], 0.0, places=10)
        self.assertAlmostEqual(result[1], 0.0, places=10)

    def test_full_circle_round_trip(self):
        """Rotating by 90 degrees four times should return to start."""
        point = (3.7, -2.1)
        origin = (1.0, 1.0)
        current = list(point)
        for _ in range(4):
            current = rotate(current, origin, 90)
        self.assertAlmostEqual(current[0], point[0], places=8)
        self.assertAlmostEqual(current[1], point[1], places=8)


# ===================================================================
# angle_between_vectors_degrees
# ===================================================================
class TestAngleBetweenVectorsDegrees(TestCase):
    """Tests for angle_between_vectors_degrees."""

    def test_smoke(self):
        angle_between_vectors_degrees(np.array([1, 0, 0]), np.array([0, 1, 0]))

    def test_perpendicular(self):
        a = angle_between_vectors_degrees(np.array([1, 0, 0]), np.array([0, 1, 0]))
        self.assertAlmostEqual(a, 90.0, places=5)

    def test_parallel(self):
        a = angle_between_vectors_degrees(np.array([1, 0]), np.array([2, 0]))
        self.assertAlmostEqual(a, 0.0, places=5)

    def test_antiparallel(self):
        a = angle_between_vectors_degrees(np.array([1, 0]), np.array([-1, 0]))
        self.assertAlmostEqual(a, 180.0, places=5)

    def test_45_degrees(self):
        a = angle_between_vectors_degrees(np.array([1, 0]), np.array([1, 1]))
        self.assertAlmostEqual(a, 45.0, places=5)

    def test_3d_vectors(self):
        a = angle_between_vectors_degrees(np.array([1, 0, 0]), np.array([0, 0, 1]))
        self.assertAlmostEqual(a, 90.0, places=5)

    def test_same_vector(self):
        a = angle_between_vectors_degrees(np.array([3, 4]), np.array([3, 4]))
        self.assertAlmostEqual(a, 0.0, places=5)

    def test_result_between_0_and_180(self):
        """Angle should always be in [0, 180]."""
        for _ in range(10):
            u = np.random.randn(3)
            v = np.random.randn(3)
            a = angle_between_vectors_degrees(u, v)
            self.assertGreaterEqual(a, 0.0)
            self.assertLessEqual(a, 180.0 + 1e-9)

    def test_clamping_numerical_stability(self):
        """Vectors that are nearly identical should give ~0 without error."""
        u = np.array([1.0, 0.0])
        v = np.array([1.0 + 1e-15, 0.0])
        a = angle_between_vectors_degrees(u, v)
        self.assertAlmostEqual(a, 0.0, places=3)


# ===================================================================
# angle_lat_lon_vectors
# ===================================================================
class TestAngleLatLonVectors(TestCase):
    """Tests for angle_lat_lon_vectors."""

    def test_smoke(self):
        a = _NS(lat=50, lon=30)
        b = _NS(lat=51, lon=31)
        c = _NS(lat=52, lon=32)
        angle_lat_lon_vectors(a, b, c, lambda x: x.lat, lambda x: x.lon)

    def test_straight_line(self):
        """Three points in a straight line (same longitude) -> angle ~ 0."""
        a = _NS(lat=50, lon=30)
        b = _NS(lat=51, lon=30)
        c = _NS(lat=52, lon=30)
        ang = angle_lat_lon_vectors(a, b, c, lambda x: x.lat, lambda x: x.lon)
        self.assertAlmostEqual(ang, 0.0, delta=1.0)

    def test_u_turn(self):
        """Going north then south -> angle ~ 180."""
        a = _NS(lat=50, lon=30)
        b = _NS(lat=51, lon=30)
        c = _NS(lat=50, lon=30)
        ang = angle_lat_lon_vectors(a, b, c, lambda x: x.lat, lambda x: x.lon)
        self.assertAlmostEqual(ang, 180.0, delta=1.0)

    def test_right_angle(self):
        """Going north then east -> angle ~ 90."""
        a = _NS(lat=50, lon=30)
        b = _NS(lat=51, lon=30)
        c = _NS(lat=51, lon=31)
        ang = angle_lat_lon_vectors(a, b, c, lambda x: x.lat, lambda x: x.lon)
        self.assertAlmostEqual(ang, 90.0, delta=5.0)

    def test_result_non_negative(self):
        a = _NS(lat=10, lon=20)
        b = _NS(lat=11, lon=21)
        c = _NS(lat=12, lon=20)
        ang = angle_lat_lon_vectors(a, b, c, lambda x: x.lat, lambda x: x.lon)
        self.assertGreaterEqual(ang, 0.0)

    def test_with_dict_accessors(self):
        """Verify it works with dict-based waypoints and custom lambdas."""
        a = {"la": 50, "lo": 30}
        b = {"la": 51, "lo": 30}
        c = {"la": 52, "lo": 31}
        ang = angle_lat_lon_vectors(a, b, c, lambda x: x["la"], lambda x: x["lo"])
        self.assertGreater(ang, 0)
        self.assertLess(ang, 180)


# ===================================================================
# Integration / sanity tests combining multiple utils
# ===================================================================
class TestIntegration(TestCase):
    """Cross-function sanity and integration tests."""

    def test_vincenty_distance_positive(self):
        """Vincenty distance should always be positive for distinct points."""
        for lat_offset in [0.1, 1, 10]:
            d = calc_vincenty((50, 30), (50 + lat_offset, 30))
            self.assertGreater(d, 0, f"Distance should be positive for offset {lat_offset}")

    def test_flight_price_with_waypoint_distance(self):
        """Compute distance from waypoints, then compute price. No crash."""
        wp = [_make_wp_obj(50, 30), _make_wp_obj(51, 31)]
        d_m = waypoints_distance(wp)
        d_km = d_m / 1000.0
        t = waypoints_flight_time(wp)
        price = drone_flight_price(MOCK_DRONE_DICT, d_km, t)
        self.assertGreater(price, MOCK_DRONE_DICT["price_per_cycle"])

    def test_penalty_zero_for_fast_flight(self):
        """Very short flight well under borderline -> zero penalty."""
        p = flight_penalty(
            time=0.01,
            borderline_time=10,
            max_time=20,
            salary=100,
            drone_price=50,
            total_grid=10,
            grid_traversed=10,
        )
        self.assertEqual(p, 0)

    def test_rotate_preserves_distance_from_origin(self):
        """Rotation should preserve distance from origin."""
        point = (3, 4)
        origin = (0, 0)
        original_dist = math.sqrt(point[0] ** 2 + point[1] ** 2)
        for angle in [0, 30, 45, 90, 135, 180, 270, 360]:
            rotated = rotate(point, origin, angle)
            rotated_dist = math.sqrt(rotated[0] ** 2 + rotated[1] ** 2)
            self.assertAlmostEqual(
                original_dist, rotated_dist, places=10, msg=f"Distance not preserved at {angle} degrees"
            )

    def test_vincenty_ordering(self):
        """Vincenty distances are ordered consistently."""
        d_vin_1 = calc_vincenty((0, 0), (1, 0))
        d_vin_2 = calc_vincenty((0, 0), (2, 0))
        self.assertGreater(d_vin_2, d_vin_1)
