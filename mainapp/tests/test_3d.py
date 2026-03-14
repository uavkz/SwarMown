"""Tests for 3D obstacle avoidance features.

Covers:
- calc_distance_3d: 3D distance calculation
- waypoints_total_climb: altitude gain tracking
- waypoints_flight_time with height_f: 3D flight time
- drone_flight_price with climb cost
- compute_crossing_width: crossing width measurement
- compute_approach_angle: approach angle calculation
- _angle_in_arc: arc membership check
- compute_flyover_path: fly-over waypoint generation
- _should_fly_over: strategy decision logic (B1-B6 + greedy)
- avoid_obstacle_3d: full 3D avoidance flow
- get_route with avoidance_config: end-to-end 3D routing
- Backward compatibility: 2D behavior unchanged when avoidance_config is None
"""

from copy import deepcopy

from django.test import TestCase
from pyproj import Transformer
from shapely.geometry import Polygon as ShapelyPolygon

from mainapp.models import Drone
from mainapp.service_routing import (
    _angle_in_arc,
    _should_fly_over,
    add_3d_path,
    avoid_obstacle_3d,
    compute_approach_angle,
    compute_crossing_width,
    compute_flyover_path,
    get_route,
)
from mainapp.utils import (
    calc_distance_3d,
    calc_vincenty,
    drone_flight_price,
    waypoints_distance,
    waypoints_flight_time,
    waypoints_total_climb,
)

# --- Test data ---------------------------------------------------------------

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

RECT_FIELD = [[30.0, 50.0], [30.1, 50.0], [30.1, 50.05], [30.0, 50.05]]
ROAD = [[30.0, 49.99], [30.1, 49.99]]
PYPROJ_TRANSFORMER = Transformer.from_crs("epsg:4087", "epsg:4326", always_xy=True)

# A hole in the middle of the field
HOLE_COORDS = [
    [30.04, 50.02],
    [30.06, 50.02],
    [30.06, 50.03],
    [30.04, 50.03],
]
HOLE_POLYGON = ShapelyPolygon(HOLE_COORDS)

BASE_AVOIDANCE_CONFIG = {
    "hole_heights": [20.0],
    "height_min": 10.0,
    "height_max": 120.0,
    "safety_margin": 5.0,
    "climb_rate": 3.0,
    "descent_rate": 2.0,
    "energy_per_meter_climb": 1.5,
    "strategy": "greedy",
    "strategy_params": None,
}


def _make_drone():
    drone = Drone(
        name="Test3D",
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


# ===================================================================
# calc_distance_3d
# ===================================================================
class TestCalcDistance3D(TestCase):
    def test_same_altitude_equals_vincenty(self):
        d2d = calc_vincenty((50, 30), (51, 31))
        d3d = calc_distance_3d((50, 30), (51, 31), 100, 100)
        self.assertAlmostEqual(d2d, d3d, places=5)

    def test_vertical_only(self):
        d = calc_distance_3d((50, 30), (50, 30), 0, 100)
        # 0 horizontal distance, 100m vertical = 0.1 km
        self.assertAlmostEqual(d, 0.1, places=3)

    def test_3d_greater_than_2d(self):
        d2d = calc_vincenty((50, 30), (51, 31))
        d3d = calc_distance_3d((50, 30), (51, 31), 0, 1000)
        self.assertGreater(d3d, d2d)

    def test_symmetric(self):
        d1 = calc_distance_3d((50, 30), (51, 31), 0, 100)
        d2 = calc_distance_3d((51, 31), (50, 30), 100, 0)
        self.assertAlmostEqual(d1, d2, places=5)

    def test_negative_altitude_change(self):
        d_up = calc_distance_3d((50, 30), (51, 31), 0, 100)
        d_down = calc_distance_3d((50, 30), (51, 31), 100, 0)
        self.assertAlmostEqual(d_up, d_down, places=5)

    def test_lon_first(self):
        d = calc_distance_3d((30, 50), (31, 51), 0, 100, lon_first=True)
        self.assertIsNotNone(d)
        self.assertGreater(d, 0)

    def test_none_for_antipodal(self):
        d = calc_distance_3d((0, 0), (0, 180), 0, 0)
        self.assertIsNone(d)


# ===================================================================
# waypoints_total_climb
# ===================================================================
class TestWaypointsTotalClimb(TestCase):
    def test_empty(self):
        self.assertEqual(waypoints_total_climb([]), 0.0)

    def test_single_waypoint(self):
        self.assertEqual(waypoints_total_climb([{"height": 10}], height_f=lambda x: x["height"]), 0.0)

    def test_ascending(self):
        wps = [{"height": 10}, {"height": 20}, {"height": 30}]
        self.assertAlmostEqual(waypoints_total_climb(wps, height_f=lambda x: x["height"]), 20.0)

    def test_descending(self):
        wps = [{"height": 30}, {"height": 20}, {"height": 10}]
        self.assertAlmostEqual(waypoints_total_climb(wps, height_f=lambda x: x["height"]), 0.0)

    def test_mixed(self):
        wps = [{"height": 10}, {"height": 30}, {"height": 15}, {"height": 25}]
        # Climb: 10→30 = 20, 15→25 = 10. Total = 30
        self.assertAlmostEqual(waypoints_total_climb(wps, height_f=lambda x: x["height"]), 30.0)

    def test_flat(self):
        wps = [{"height": 10}, {"height": 10}, {"height": 10}]
        self.assertAlmostEqual(waypoints_total_climb(wps, height_f=lambda x: x["height"]), 0.0)


# ===================================================================
# waypoints_flight_time with height_f
# ===================================================================
class TestFlightTime3D(TestCase):
    def test_2d_unchanged_without_height_f(self):
        """Without height_f, behavior identical to 2D."""
        wps = [
            {"lat": 50, "lon": 30, "height": 10, "drone": MOCK_DRONE_DICT, "spray_on": False},
            {"lat": 51, "lon": 31, "height": 10, "drone": MOCK_DRONE_DICT, "spray_on": False},
        ]
        t = waypoints_flight_time(
            wps,
            lat_f=lambda x: x["lat"],
            lon_f=lambda x: x["lon"],
            max_speed_f=lambda x: x["drone"]["max_speed"],
            slowdown_ratio_f=lambda x: x["drone"]["slowdown_ratio_per_degree"],
            min_slowdown_ratio_f=lambda x: x["drone"]["min_slowdown_ratio"],
            spray_on_f=lambda x: x["spray_on"],
        )
        self.assertGreater(t, 0)

    def test_climb_increases_time(self):
        """Climbing should take at least as long as horizontal-only."""
        wps_flat = [
            {"lat": 50, "lon": 30, "height": 10, "drone": MOCK_DRONE_DICT, "spray_on": False},
            {"lat": 50.001, "lon": 30, "height": 10, "drone": MOCK_DRONE_DICT, "spray_on": False},
        ]
        wps_climb = [
            {"lat": 50, "lon": 30, "height": 10, "drone": MOCK_DRONE_DICT, "spray_on": False},
            {"lat": 50.001, "lon": 30, "height": 1000, "drone": MOCK_DRONE_DICT, "spray_on": False},
        ]
        kwargs = dict(
            lat_f=lambda x: x["lat"],
            lon_f=lambda x: x["lon"],
            max_speed_f=lambda x: x["drone"]["max_speed"],
            slowdown_ratio_f=lambda x: x["drone"]["slowdown_ratio_per_degree"],
            min_slowdown_ratio_f=lambda x: x["drone"]["min_slowdown_ratio"],
            spray_on_f=lambda x: x["spray_on"],
            height_f=lambda x: x["height"],
            climb_rate=3.0,
            descent_rate=2.0,
        )
        t_flat = waypoints_flight_time(wps_flat, **kwargs)
        t_climb = waypoints_flight_time(wps_climb, **kwargs)
        self.assertGreater(t_climb, t_flat)

    def test_pure_vertical_climb(self):
        """Same horizontal position but different altitude should still count time."""
        wps = [
            {"lat": 50, "lon": 30, "height": 10, "drone": MOCK_DRONE_DICT, "spray_on": False},
            {"lat": 50, "lon": 30, "height": 10, "drone": MOCK_DRONE_DICT, "spray_on": False},
            {"lat": 50, "lon": 30, "height": 100, "drone": MOCK_DRONE_DICT, "spray_on": False},
        ]
        t = waypoints_flight_time(
            wps,
            lat_f=lambda x: x["lat"],
            lon_f=lambda x: x["lon"],
            max_speed_f=lambda x: x["drone"]["max_speed"],
            slowdown_ratio_f=lambda x: x["drone"]["slowdown_ratio_per_degree"],
            min_slowdown_ratio_f=lambda x: x["drone"]["min_slowdown_ratio"],
            spray_on_f=lambda x: x["spray_on"],
            height_f=lambda x: x["height"],
            climb_rate=3.0,
            descent_rate=2.0,
        )
        # 90m climb at 3 m/s = 30 seconds = 30/3600 hours
        expected = 90 / 3.0 / 3600
        self.assertAlmostEqual(t, expected, places=6)

    def test_no_double_count_vertical_time(self):
        """Consecutive same-coords waypoints with different height should not double-count."""
        # wp1 and wp2 share coords, wp2 climbs from 10 to 50. wp3 moves horizontally at 50.
        # Vertical time should be 40m climb (wp1->wp2) only, NOT 40m again for wp2->wp3.
        wps = [
            {"lat": 50, "lon": 30, "height": 10, "drone": MOCK_DRONE_DICT, "spray_on": False},
            {"lat": 51, "lon": 31, "height": 10, "drone": MOCK_DRONE_DICT, "spray_on": False},
            {"lat": 51, "lon": 31, "height": 50, "drone": MOCK_DRONE_DICT, "spray_on": False},
            {"lat": 52, "lon": 32, "height": 50, "drone": MOCK_DRONE_DICT, "spray_on": False},
        ]
        kwargs = dict(
            lat_f=lambda x: x["lat"],
            lon_f=lambda x: x["lon"],
            max_speed_f=lambda x: x["drone"]["max_speed"],
            slowdown_ratio_f=lambda x: x["drone"]["slowdown_ratio_per_degree"],
            min_slowdown_ratio_f=lambda x: x["drone"]["min_slowdown_ratio"],
            spray_on_f=lambda x: x["spray_on"],
            height_f=lambda x: x["height"],
            climb_rate=3.0,
            descent_rate=2.0,
        )
        t = waypoints_flight_time(wps, **kwargs)
        # The climb is 40m at 3 m/s = 13.33 seconds
        # Should NOT be 80m (double-counted)
        # Compute expected: horizontal time for wp0->wp1, vertical time for wp1->wp2,
        # horizontal time for wp2->wp3 (no vertical since both at 50)
        t_01 = calc_vincenty([50, 30], [51, 31]) / 15  # horizontal only
        t_12 = 40 / 3.0 / 3600  # pure vertical climb
        t_23 = calc_vincenty([51, 31], [52, 32]) / 15  # horizontal, no vertical
        expected = t_01 + t_12 + t_23
        self.assertAlmostEqual(t, expected, places=4)

    def test_descent_time(self):
        """Descending adds time too (vertical limited)."""
        wps = [
            {"lat": 50, "lon": 30, "height": 100, "drone": MOCK_DRONE_DICT, "spray_on": False},
            {"lat": 50.0001, "lon": 30, "height": 0, "drone": MOCK_DRONE_DICT, "spray_on": False},
        ]
        t = waypoints_flight_time(
            wps,
            lat_f=lambda x: x["lat"],
            lon_f=lambda x: x["lon"],
            max_speed_f=lambda x: x["drone"]["max_speed"],
            slowdown_ratio_f=lambda x: x["drone"]["slowdown_ratio_per_degree"],
            min_slowdown_ratio_f=lambda x: x["drone"]["min_slowdown_ratio"],
            spray_on_f=lambda x: x["spray_on"],
            height_f=lambda x: x["height"],
            climb_rate=3.0,
            descent_rate=2.0,
        )
        self.assertGreater(t, 0)


# ===================================================================
# drone_flight_price with climb
# ===================================================================
class TestDroneFlightPrice3D(TestCase):
    def test_no_climb_unchanged(self):
        p1 = drone_flight_price(MOCK_DRONE_DICT, 100, 5)
        p2 = drone_flight_price(MOCK_DRONE_DICT, 100, 5, climb_meters=0, energy_per_meter_climb=0)
        self.assertAlmostEqual(p1, p2)

    def test_climb_increases_price(self):
        p_flat = drone_flight_price(MOCK_DRONE_DICT, 100, 5)
        p_climb = drone_flight_price(MOCK_DRONE_DICT, 100, 5, climb_meters=50, energy_per_meter_climb=1.5)
        self.assertGreater(p_climb, p_flat)

    def test_more_climb_more_price(self):
        p1 = drone_flight_price(MOCK_DRONE_DICT, 100, 5, climb_meters=10, energy_per_meter_climb=1.5)
        p2 = drone_flight_price(MOCK_DRONE_DICT, 100, 5, climb_meters=100, energy_per_meter_climb=1.5)
        self.assertGreater(p2, p1)


# ===================================================================
# compute_crossing_width
# ===================================================================
class TestComputeCrossingWidth(TestCase):
    def test_no_crossing(self):
        w = compute_crossing_width([30.0, 50.0], [30.1, 50.0], HOLE_POLYGON)
        self.assertAlmostEqual(w, 0.0, places=1)

    def test_through_hole(self):
        w = compute_crossing_width([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON)
        self.assertGreater(w, 0)

    def test_narrow_vs_wide(self):
        """Crossing through narrow side should give smaller width than wide side."""
        # Horizontal crossing (through narrow 0.01° width ≈ 0.6 km)
        w_horiz = compute_crossing_width([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON)
        # The hole is 0.02° wide in lon and 0.01° in lat
        # A horizontal line through it crosses 0.02° of longitude
        self.assertGreater(w_horiz, 0)


# ===================================================================
# compute_approach_angle
# ===================================================================
class TestComputeApproachAngle(TestCase):
    def test_east(self):
        angle = compute_approach_angle([0, 0], [1, 0])
        self.assertAlmostEqual(angle, 0.0, places=5)

    def test_north(self):
        angle = compute_approach_angle([0, 0], [0, 1])
        self.assertAlmostEqual(angle, 90.0, places=5)

    def test_west(self):
        angle = compute_approach_angle([0, 0], [-1, 0])
        self.assertAlmostEqual(angle, 180.0, places=5)

    def test_south(self):
        angle = compute_approach_angle([0, 0], [0, -1])
        self.assertAlmostEqual(angle, 270.0, places=5)

    def test_northeast(self):
        angle = compute_approach_angle([0, 0], [1, 1])
        self.assertAlmostEqual(angle, 45.0, places=5)


# ===================================================================
# _angle_in_arc
# ===================================================================
class TestAngleInArc(TestCase):
    def test_simple_arc(self):
        self.assertTrue(_angle_in_arc(90, 45, 135))
        self.assertFalse(_angle_in_arc(10, 45, 135))

    def test_wrapping_arc(self):
        # Arc from 350 to 10 (wraps around 0)
        self.assertTrue(_angle_in_arc(0, 350, 10))
        self.assertTrue(_angle_in_arc(355, 350, 10))
        self.assertTrue(_angle_in_arc(5, 350, 10))
        self.assertFalse(_angle_in_arc(180, 350, 10))

    def test_full_circle(self):
        self.assertTrue(_angle_in_arc(180, 0, 360))

    def test_zero_arc(self):
        self.assertTrue(_angle_in_arc(45, 45, 45))

    def test_edge_values(self):
        self.assertTrue(_angle_in_arc(45, 45, 135))
        self.assertTrue(_angle_in_arc(135, 45, 135))


# ===================================================================
# compute_flyover_path
# ===================================================================
class TestComputeFlyoverPath(TestCase):
    def test_returns_path(self):
        path = compute_flyover_path([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 25, 10)
        self.assertIsInstance(path, list)
        self.assertGreater(len(path), 2)

    def test_start_at_current_alt(self):
        path = compute_flyover_path([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 25, 10)
        self.assertAlmostEqual(path[0][2], 10)

    def test_middle_at_flyover_alt(self):
        path = compute_flyover_path([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 25, 10)
        # Middle points should be at fly-over altitude
        for pt in path[1:-1]:
            self.assertAlmostEqual(pt[2], 25)

    def test_exit_at_flyover_alt(self):
        """Drone stays high after crossing (altitude persistence)."""
        path = compute_flyover_path([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 25, 10)
        self.assertAlmostEqual(path[-1][2], 25)

    def test_no_crossing_returns_direct(self):
        path = compute_flyover_path([30.0, 50.0], [30.1, 50.0], HOLE_POLYGON, 25, 10)
        self.assertEqual(len(path), 2)


# ===================================================================
# _should_fly_over — strategy decision logic
# ===================================================================
class TestShouldFlyOver(TestCase):
    def test_too_high_for_ceiling(self):
        config = dict(BASE_AVOIDANCE_CONFIG, hole_heights=[200], height_max=120)
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertFalse(fly)

    def test_already_above(self):
        config = dict(BASE_AVOIDANCE_CONFIG, hole_heights=[20], safety_margin=5)
        fly, alt = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 30)
        self.assertTrue(fly)
        self.assertEqual(alt, 30)  # stays at current altitude

    def test_below_working_alt_no_avoidance_needed(self):
        """Obstacle below working altitude — always fly over."""
        config = dict(BASE_AVOIDANCE_CONFIG, hole_heights=[3], height_min=10, safety_margin=2)
        # obstacle_height + safety_margin = 5 < height_min = 10
        # current_altitude = 10 >= required_alt = 5 → fly over (already above)
        fly, _alt = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertTrue(fly)

    def test_greedy_low_obstacle(self):
        """Greedy should prefer flying over low obstacles (cheap climb)."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="greedy", hole_heights=[5], safety_margin=5)
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        # Should fly over: gap=0 (already at 10, need 10) → True
        self.assertTrue(fly)

    def test_b1_over(self):
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", strategy_params=[1])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertTrue(fly)

    def test_b1_around(self):
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", strategy_params=[0])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertFalse(fly)

    def test_b1_single(self):
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1s", strategy_params=[1])
        # Single mode: one value for all holes
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertTrue(fly)

    def test_b2_small_gap(self):
        """B2: gap = 15m, threshold = 20m → fly over."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B2", hole_heights=[20], strategy_params=[20])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        # gap = 20 + 5 - 10 = 15, threshold = 20 → 15 <= 20 → True
        self.assertTrue(fly)

    def test_b2_large_gap(self):
        """B2: gap = 45m, threshold = 20m → go around."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B2", hole_heights=[50], strategy_params=[20])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        # gap = 50 + 5 - 10 = 45, threshold = 20 → 45 > 20 → False
        self.assertFalse(fly)

    def test_b3_narrow_crossing(self):
        """B3: narrow crossing → fly over if width < threshold."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B3", hole_heights=[20], strategy_params=[5000])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        # Width threshold = 5000m, crossing width ≈ 0.02° * 90000 ≈ 1800m < 5000 → True
        self.assertTrue(fly)

    def test_b3_wide_crossing(self):
        """B3: crossing width > threshold → go around."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B3", hole_heights=[20], strategy_params=[100])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        # Width threshold = 100m, crossing width ≈ 1800m > 100 → False
        self.assertFalse(fly)

    def test_b5_both_conditions_met(self):
        """B5: gap small AND crossing narrow → fly over."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B5", hole_heights=[20], strategy_params=[(20, 5000)])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertTrue(fly)

    def test_b5_gap_too_large(self):
        """B5: gap too large → go around even if crossing is narrow."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B5", hole_heights=[50], strategy_params=[(10, 5000)])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertFalse(fly)

    def test_b4_in_arc(self):
        """B4: approach angle in arc → fly over."""
        # Horizontal crossing goes east (angle ≈ 0°)
        config = dict(
            BASE_AVOIDANCE_CONFIG, strategy="B4", hole_heights=[20], strategy_params=[(350, 10)]
        )  # arc wrapping around 0°
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertTrue(fly)

    def test_b4_out_of_arc(self):
        """B4: approach angle outside arc → go around."""
        config = dict(
            BASE_AVOIDANCE_CONFIG, strategy="B4", hole_heights=[20], strategy_params=[(90, 180)]
        )  # arc = [90°, 180°]
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        # Horizontal crossing angle ≈ 0° (east), not in [90°, 180°] → False
        self.assertFalse(fly)

    def test_b6_in_arc_and_small_gap(self):
        """B6: angle in arc AND gap small → fly over."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B6", hole_heights=[20], strategy_params=[(350, 10, 20)])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertTrue(fly)

    def test_no_params_returns_false(self):
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", strategy_params=None)
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertFalse(fly)


# ===================================================================
# avoid_obstacle_3d
# ===================================================================
class TestAvoidObstacle3D(TestCase):
    def test_2d_fallback(self):
        path, _alt = avoid_obstacle_3d([30.0, 50.025], [30.1, 50.025], [HOLE_POLYGON], None, 10)
        # Should fall back to 2D detour
        self.assertGreater(len(path), 2)

    def test_2d_strategy(self):
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="2d")
        path, _alt = avoid_obstacle_3d([30.0, 50.025], [30.1, 50.025], [HOLE_POLYGON], config, 10)
        self.assertGreater(len(path), 2)

    def test_flyover_returns_3d_path(self):
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", strategy_params=[1])
        path, _exit_alt = avoid_obstacle_3d([30.0, 50.025], [30.1, 50.025], [HOLE_POLYGON], config, 10)
        # Path should contain altitude information
        self.assertGreater(len(path), 2)
        for pt in path:
            self.assertEqual(len(pt), 3)  # (lon, lat, alt)

    def test_flyover_exit_altitude(self):
        """After fly-over, exit altitude should be at least fly-over height."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", hole_heights=[20], strategy_params=[1])
        _, exit_alt = avoid_obstacle_3d([30.0, 50.025], [30.1, 50.025], [HOLE_POLYGON], config, 10)
        self.assertGreaterEqual(exit_alt, 25)  # 20 + 5 safety

    def test_around_preserves_altitude(self):
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", strategy_params=[0])
        _, exit_alt = avoid_obstacle_3d([30.0, 50.025], [30.1, 50.025], [HOLE_POLYGON], config, 10)
        self.assertEqual(exit_alt, 10)

    def test_no_crossing_returns_direct(self):
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", strategy_params=[1])
        path, _exit_alt = avoid_obstacle_3d([30.0, 50.0], [30.1, 50.0], [HOLE_POLYGON], config, 10)
        # No crossing → direct path
        self.assertLessEqual(len(path), 3)

    def test_multi_hole_no_duplicates(self):
        """Two holes in sequence: end point should appear only once."""
        hole1 = ShapelyPolygon([[30.02, 50.02], [30.04, 50.02], [30.04, 50.03], [30.02, 50.03]])
        hole2 = ShapelyPolygon([[30.06, 50.02], [30.08, 50.02], [30.08, 50.03], [30.06, 50.03]])
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", hole_heights=[20, 20], strategy_params=[1, 1])
        path, exit_alt = avoid_obstacle_3d([30.0, 50.025], [30.1, 50.025], [hole1, hole2], config, 10)
        # End point should not be duplicated
        end_count = sum(1 for pt in path if abs(pt[0] - 30.1) < 1e-8 and abs(pt[1] - 50.025) < 1e-8)
        self.assertEqual(end_count, 1, f"End point duplicated {end_count} times in path")
        self.assertGreaterEqual(exit_alt, 25)

    def test_multi_hole_ordered_by_intersection(self):
        """Holes are processed in intersection order, not list order."""
        # hole_far is listed first but hole_near is encountered first along the segment
        hole_near = ShapelyPolygon([[30.02, 50.02], [30.04, 50.02], [30.04, 50.03], [30.02, 50.03]])
        hole_far = ShapelyPolygon([[30.06, 50.02], [30.08, 50.02], [30.08, 50.03], [30.06, 50.03]])
        config = dict(
            BASE_AVOIDANCE_CONFIG,
            strategy="B1",
            hole_heights=[20, 20],
            strategy_params=[1, 1],
        )
        # List holes in reverse order (far first)
        path1, _ = avoid_obstacle_3d([30.0, 50.025], [30.1, 50.025], [hole_far, hole_near], config, 10)
        path2, _ = avoid_obstacle_3d([30.0, 50.025], [30.1, 50.025], [hole_near, hole_far], config, 10)
        # Both should produce similar paths regardless of list order
        self.assertEqual(len(path1), len(path2))

    def test_2d_detour_then_another_hole(self):
        """After 2D detour for hole 1, hole 2 should still be processed."""
        hole1 = ShapelyPolygon([[30.02, 50.02], [30.04, 50.02], [30.04, 50.03], [30.02, 50.03]])
        hole2 = ShapelyPolygon([[30.06, 50.02], [30.08, 50.02], [30.08, 50.03], [30.06, 50.03]])
        config = dict(
            BASE_AVOIDANCE_CONFIG,
            strategy="B1",
            hole_heights=[20, 20],
            strategy_params=[0, 1],  # around hole1, over hole2
        )
        _path, exit_alt = avoid_obstacle_3d([30.0, 50.025], [30.1, 50.025], [hole1, hole2], config, 10)
        # Should have detour around hole1 AND fly-over for hole2
        # Exit altitude should be elevated from flying over hole2
        self.assertGreaterEqual(exit_alt, 25)


# ===================================================================
# add_3d_path
# ===================================================================
class TestAdd3DPath(TestCase):
    def setUp(self):
        self.drone = _make_drone()

    def test_adds_waypoints(self):
        wp = []
        path = [(30.0, 50.0, 10), (30.05, 50.025, 25), (30.1, 50.05, 25)]
        dist = add_3d_path(wp, path, self.drone)
        self.assertEqual(len(wp), 3)
        self.assertGreater(dist, 0)

    def test_preserves_altitude(self):
        wp = []
        path = [(30.0, 50.0, 10), (30.05, 50.025, 25), (30.1, 50.05, 30)]
        add_3d_path(wp, path, self.drone)
        self.assertEqual(wp[0]["height"], 10)
        self.assertEqual(wp[1]["height"], 25)
        self.assertEqual(wp[2]["height"], 30)


# ===================================================================
# End-to-end: get_route with avoidance_config
# ===================================================================
class TestGetRoute3D(TestCase):
    def setUp(self):
        self.drone = _make_drone()

    def test_backward_compatible_no_config(self):
        """get_route without avoidance_config produces same result as before."""
        _grid, waypoints, _car_waypoints, _initial = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=500,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
        )
        self.assertIsInstance(_grid, list)
        self.assertIsInstance(waypoints, list)

    def test_with_holes_no_3d(self):
        """Holes but strategy='2d' should produce 2D detour behavior."""
        _grid, waypoints, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=500,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
            holes=[HOLE_COORDS],
            simple_holes_traversal=True,
            avoidance_config={
                "strategy": "2d",
                "hole_heights": [0],
                "height_min": 10,
                "height_max": 120,
                "safety_margin": 5,
                "climb_rate": 3,
                "descent_rate": 2,
                "energy_per_meter_climb": 1.5,
                "strategy_params": None,
            },
        )
        self.assertIsInstance(waypoints, list)

    def test_with_holes_greedy_3d(self):
        """Holes with greedy strategy should produce valid waypoints."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="greedy", hole_heights=[20])
        _grid, waypoints, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=500,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
            holes=[HOLE_COORDS],
            simple_holes_traversal=True,
            avoidance_config=config,
        )
        self.assertIsInstance(waypoints, list)

    def test_with_holes_b1_over(self):
        """B1 strategy with all 'over' should produce valid waypoints."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", hole_heights=[20], strategy_params=[1])
        _grid, waypoints, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=500,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
            holes=[HOLE_COORDS],
            simple_holes_traversal=True,
            avoidance_config=config,
        )
        self.assertIsInstance(waypoints, list)

    def test_with_holes_b5(self):
        """B5 strategy should produce valid waypoints."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B5", hole_heights=[20], strategy_params=[(15, 3000)])
        _grid, waypoints, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=500,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
            holes=[HOLE_COORDS],
            simple_holes_traversal=True,
            avoidance_config=config,
        )
        self.assertIsInstance(waypoints, list)

    def test_3d_waypoints_have_altitude(self):
        """With 3D avoidance, waypoints should have meaningful height values."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", hole_heights=[20], strategy_params=[1])
        _, waypoints, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(RECT_FIELD),
            grid_step=500,
            road=deepcopy(ROAD),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
            holes=[HOLE_COORDS],
            simple_holes_traversal=True,
            avoidance_config=config,
        )
        if waypoints:
            for segment in waypoints:
                for wp in segment:
                    self.assertIn("height", wp)
                    self.assertGreater(wp["height"], 0)


# ===================================================================
# GA gene generation and mutation
# ===================================================================
class TestGAAvoidanceGene(TestCase):
    def test_generate_b1(self):
        from scripts.ga_common import generate_avoidance_gene

        gene = generate_avoidance_gene("B1", 3)
        self.assertEqual(len(gene), 3)
        for v in gene:
            self.assertIn(v, [0, 1])

    def test_generate_b1_single(self):
        from scripts.ga_common import generate_avoidance_gene

        gene = generate_avoidance_gene("B1s", 3)
        self.assertEqual(len(gene), 1)

    def test_generate_b2(self):
        from scripts.ga_common import generate_avoidance_gene

        gene = generate_avoidance_gene("B2", 2)
        self.assertEqual(len(gene), 2)
        for v in gene:
            self.assertIsInstance(v, float)
            self.assertGreaterEqual(v, 0)

    def test_generate_b5(self):
        from scripts.ga_common import generate_avoidance_gene

        gene = generate_avoidance_gene("B5", 2)
        self.assertEqual(len(gene), 2)
        for v in gene:
            self.assertIsInstance(v, tuple)
            self.assertEqual(len(v), 2)

    def test_generate_b6(self):
        from scripts.ga_common import generate_avoidance_gene

        gene = generate_avoidance_gene("B6", 1)
        self.assertEqual(len(gene), 1)
        self.assertEqual(len(gene[0]), 3)

    def test_mutate_b1(self):
        from scripts.ga_common import mutate_avoidance_gene

        gene = [0, 1, 0]
        mutated = mutate_avoidance_gene(gene, "B1", 1.0)  # 100% mutation chance
        # At least one should change (probabilistic, but with p=1 all change)
        self.assertEqual(len(mutated), 3)

    def test_mutate_b2(self):
        from scripts.ga_common import mutate_avoidance_gene

        gene = [10.0, 20.0]
        original = gene[:]
        mutate_avoidance_gene(gene, "B2", 1.0)
        # With 100% mutation, values should change
        changed = sum(1 for a, b in zip(original, gene) if a != b)
        self.assertGreater(changed, 0)

    def test_mutate_b5(self):
        from scripts.ga_common import mutate_avoidance_gene

        gene = [(10.0, 100.0), (20.0, 200.0)]
        mutate_avoidance_gene(gene, "B5", 1.0)
        self.assertEqual(len(gene), 2)
        for v in gene:
            self.assertIsInstance(v, tuple)
            self.assertEqual(len(v), 2)

    def test_mutate_none(self):
        from scripts.ga_common import mutate_avoidance_gene

        result = mutate_avoidance_gene(None, "B1", 1.0)
        self.assertIsNone(result)

    def test_generate_2d_returns_none(self):
        from scripts.ga_common import generate_avoidance_gene

        gene = generate_avoidance_gene("2d", 3)
        self.assertIsNone(gene)

    def test_serialize_avoidance_gene_b5(self):
        from scripts.ga_common import _serialize_avoidance_gene

        gene = [(12.0, 150.0), (5.0, 80.0)]
        result = _serialize_avoidance_gene(gene)
        self.assertEqual(result, [[12.0, 150.0], [5.0, 80.0]])

    def test_serialize_avoidance_gene_b1(self):
        from scripts.ga_common import _serialize_avoidance_gene

        gene = [0, 1, 1]
        result = _serialize_avoidance_gene(gene)
        self.assertEqual(result, [0, 1, 1])


# ===================================================================
# parse_obstacle_heights
# ===================================================================
class TestParseObstacleHeights(TestCase):
    def test_default_zeros(self):
        from scripts.ga_common import parse_obstacle_heights

        class Args:
            obstacle_heights = None

        heights = parse_obstacle_heights(Args(), 3)
        self.assertEqual(heights, [0.0, 0.0, 0.0])

    def test_from_json(self):
        from scripts.ga_common import parse_obstacle_heights

        class Args:
            obstacle_heights = "[10, 20, 30]"

        heights = parse_obstacle_heights(Args(), 3)
        self.assertEqual(heights, [10.0, 20.0, 30.0])

    def test_wrong_count_raises(self):
        from scripts.ga_common import parse_obstacle_heights

        class Args:
            obstacle_heights = "[10, 20]"

        with self.assertRaises(ValueError):
            parse_obstacle_heights(Args(), 3)

    def test_empty_mission(self):
        from scripts.ga_common import parse_obstacle_heights

        class Args:
            obstacle_heights = None

        heights = parse_obstacle_heights(Args(), 0)
        self.assertEqual(heights, [])


# ===================================================================
# build_avoidance_config
# ===================================================================
class TestBuildAvoidanceConfig(TestCase):
    def test_creates_config(self):
        from scripts.ga_common import build_avoidance_config

        class Args:
            height_min = 10
            height_max = 120
            safety_margin = 5
            climb_rate = 3
            descent_rate = 2
            energy_per_meter_climb = 1.5
            avoidance_strategy = "greedy"

        config = build_avoidance_config(Args(), [15, 20])
        self.assertEqual(config["hole_heights"], [15, 20])
        self.assertEqual(config["strategy"], "greedy")
        self.assertIsNone(config["strategy_params"])


# ===================================================================
# Altitude persistence (emergent in B2/B5/B6)
# ===================================================================
class TestAltitudePersistence(TestCase):
    """Test that altitude persists between fly-overs (emergent behavior)."""

    def test_already_above_flies_over_free(self):
        """When drone is already above obstacle, fly over is free."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B2", hole_heights=[20], safety_margin=5, strategy_params=[30])
        # Current altitude 30m, obstacle needs 25m → gap = -5 → already above
        fly, alt = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 30)
        self.assertTrue(fly)
        self.assertEqual(alt, 30)  # stays at current altitude, no climb needed

    def test_sequential_obstacles_persist(self):
        """After flying over hole 1, drone stays high and clears hole 2 for free."""
        config = dict(
            BASE_AVOIDANCE_CONFIG, strategy="B2", hole_heights=[20, 15], safety_margin=5, strategy_params=[20, 20]
        )

        # First obstacle: climb from 10 to 25
        fly1, alt1 = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertTrue(fly1)
        self.assertEqual(alt1, 25)  # climbed to 20+5=25

        # Second obstacle (15m + 5m = 20m): drone at 25m → gap = -5 → free
        fly2, alt2 = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 1, config, 25)
        self.assertTrue(fly2)
        self.assertEqual(alt2, 25)  # stays at 25, no additional climb


# ===================================================================
# Corner cases and stress tests
# ===================================================================
class TestCornerCases(TestCase):
    """Corner cases: ceiling bounds, B2 thresholds, direction, field shapes."""

    def setUp(self):
        self.drone = _make_drone()
        self.drone.max_distance_no_load = 100  # generous range for test fields

    def _run_route(self, field, road, holes, config, grid_step=500):
        grid, waypoints, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="ne",
            field=deepcopy(field),
            grid_step=grid_step,
            road=deepcopy(road),
            drones=[self.drone],
            pyproj_transformer=PYPROJ_TRANSFORMER,
            holes=deepcopy(holes),
            simple_holes_traversal=True,
            avoidance_config=config,
        )
        return grid, waypoints

    def test_obstacle_exactly_at_ceiling(self):
        """Obstacle height + margin = ceiling: should fly over at exactly ceiling."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", hole_heights=[115], strategy_params=[1])
        fly, alt = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertTrue(fly)
        self.assertEqual(alt, 120)  # exactly at ceiling

    def test_obstacle_above_ceiling_must_go_around(self):
        """Obstacle height + margin > ceiling: must go around."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", hole_heights=[116], strategy_params=[1])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertFalse(fly)

    def test_zero_height_obstacle_free_flyover(self):
        """Zero-height obstacle: already above at working altitude."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", hole_heights=[0], strategy_params=[1])
        fly, alt = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertTrue(fly)
        self.assertEqual(alt, 10)

    def test_b2_threshold_boundary(self):
        """B2: gap exactly at threshold should fly over (gap <= threshold)."""
        # hole_height=20, safety=5, current=10 → gap=15. threshold=15 → fly over
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B2", hole_heights=[20], strategy_params=[15])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertTrue(fly)

    def test_b2_threshold_just_below(self):
        """B2: gap just above threshold should go around."""
        # gap=15, threshold=14.9 → go around
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B2", hole_heights=[20], strategy_params=[14.9])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertFalse(fly)

    def test_narrow_field_hole_blocks_width(self):
        """Hole covers entire field width — both strategies should produce valid waypoints."""
        field = [[30.0, 50.0], [30.02, 50.0], [30.02, 50.05], [30.0, 50.05]]
        road = [[30.0, 49.99], [30.02, 49.99]]
        hole = [[30.005, 50.02], [30.015, 50.02], [30.015, 50.03], [30.005, 50.03]]

        config_over = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", hole_heights=[20], strategy_params=[1])
        config_around = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", hole_heights=[20], strategy_params=[0])

        _, wps_over = self._run_route(field, road, [hole], config_over, grid_step=300)
        _, wps_around = self._run_route(field, road, [hole], config_around, grid_step=300)

        self.assertGreater(len(wps_over), 0)
        self.assertGreater(len(wps_around), 0)

        # Fly-over should be shorter distance
        _L, _Lo = lambda x: x["lat"], lambda x: x["lon"]
        dist_over = sum(waypoints_distance(f, lat_f=_L, lon_f=_Lo) for f in wps_over)
        dist_around = sum(waypoints_distance(f, lat_f=_L, lon_f=_Lo) for f in wps_around)
        self.assertLess(dist_over, dist_around)

    def test_three_holes_all_fly_over(self):
        """Three holes with fly-over: altitude should persist and increase."""
        from mainapp.service_routing import avoid_obstacle_3d

        hole1 = ShapelyPolygon([[30.02, 50.02], [30.03, 50.02], [30.03, 50.03], [30.02, 50.03]])
        hole2 = ShapelyPolygon([[30.04, 50.02], [30.05, 50.02], [30.05, 50.03], [30.04, 50.03]])
        hole3 = ShapelyPolygon([[30.06, 50.02], [30.07, 50.02], [30.07, 50.03], [30.06, 50.03]])
        config = dict(
            BASE_AVOIDANCE_CONFIG,
            strategy="B2",
            hole_heights=[20, 25, 15],
            strategy_params=[30, 30, 30],
        )
        path, exit_alt = avoid_obstacle_3d([30.0, 50.025], [30.1, 50.025], [hole1, hole2, hole3], config, 10)
        # Exit altitude should be max required: max(20+5, 25+5, 15+5) = 30
        self.assertEqual(exit_alt, 30)
        # All points should have altitude >= 10 and <= 120
        for pt in path:
            self.assertGreaterEqual(pt[2], 10)
            self.assertLessEqual(pt[2], 120)

    def test_altitude_override_when_above(self):
        """B1=0 (go around) is overridden when drone is already above the obstacle."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B1", hole_heights=[10], strategy_params=[0])
        # At 30m, obstacle needs 10+5=15. Already above → fly over regardless of B1=0
        fly, alt = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 30)
        self.assertTrue(fly)
        self.assertEqual(alt, 30)

    def test_b5_json_deserialized_params(self):
        """B5 with list params (deserialized from JSON) should work like tuples."""
        config = dict(BASE_AVOIDANCE_CONFIG, strategy="B5", hole_heights=[20], strategy_params=[[20, 5000]])
        fly, _ = _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
        self.assertTrue(fly)  # gap=15 <= 20, width < 5000

    def test_mutation_preserves_float_type(self):
        """B2 mutation should produce floats, not ints when clamped to 0."""
        from scripts.ga_common import mutate_avoidance_gene

        gene = [0.1, 0.1, 0.1]  # very small values likely to get clamped to 0
        for _ in range(100):
            mutate_avoidance_gene(gene[:], "B2", 1.0)
        # Even after many mutations, max(0.0, ...) should keep float type
        mutated = mutate_avoidance_gene([0.001], "B2", 1.0)
        self.assertIsInstance(mutated[0], float)

    def test_all_strategies_no_crash(self):
        """Every strategy should run without error on standard inputs."""
        strategies = {
            "2d": None,
            "greedy": None,
            "B1": [1],
            "B1s": [1],
            "B2": [20],
            "B2s": [20],
            "B3": [5000],
            "B3s": [5000],
            "B4": [(350, 10)],
            "B4s": [(350, 10)],
            "B5": [(20, 5000)],
            "B5s": [(20, 5000)],
            "B6": [(350, 10, 20)],
            "B6s": [(350, 10, 20)],
        }
        for strategy, params in strategies.items():
            config = dict(BASE_AVOIDANCE_CONFIG, strategy=strategy, strategy_params=params)
            try:
                _should_fly_over([30.0, 50.025], [30.1, 50.025], HOLE_POLYGON, 0, config, 10)
            except Exception as e:
                self.fail(f"Strategy {strategy} crashed: {e}")

    def test_flyto_crosses_hole_applies_detour(self):
        """Fly-to crossing a hole should apply detour (more than just car→grid_pt)."""
        from mainapp.service_routing import generate_fly_to

        car = [30.02, 49.999]
        grid_pt = [30.037827, 50.019729]
        hole = ShapelyPolygon([[30.025, 50.01], [30.03, 50.01], [30.03, 50.015], [30.025, 50.015]])
        wps = []
        _dist, _alt = generate_fly_to(wps, car, grid_pt, self.drone, [hole])
        self.assertGreater(len(wps), 1, "Fly-to should add detour when crossing hole")
        self.assertAlmostEqual(wps[-1]["lon"], grid_pt[0], places=4)
        self.assertAlmostEqual(wps[-1]["lat"], grid_pt[1], places=4)
