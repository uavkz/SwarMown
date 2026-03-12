"""
End-to-end tests for the SwarMown routing pipeline.

Exercises the full flow: create DB models -> generate route -> validate waypoints
-> check cost calculations make sense.
"""

import json
from copy import deepcopy

from django.contrib.auth.models import User
from django.test import TestCase
from pyproj import Transformer
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry.polygon import Polygon as ShapelyPolygon

from mainapp.models import Drone, Field
from mainapp.service_routing import get_route
from mainapp.utils import (
    drone_flight_price,
    flight_penalty,
    transform_to_equidistant,
    transform_to_lat_lon,
    waypoints_distance,
    waypoints_flight_time,
)

# A real-ish rectangular field (roughly 5km x 3km near Almaty, Kazakhstan)
FIELD_POINTS = [[76.9, 43.2], [76.95, 43.2], [76.95, 43.23], [76.9, 43.23]]
ROAD_POINTS = [[76.9, 43.195], [76.95, 43.195]]

# Transformer matching the internal projection (epsg:4087 equidistant)
TRANSFORMER = Transformer.from_crs("epsg:4087", "epsg:4326", always_xy=True)

# Required keys every waypoint dict must carry
REQUIRED_WP_KEYS = {"lat", "lon", "height", "drone", "spray_on"}


def _make_drone(name="TestDrone-1", model="DJI-T30", **overrides):
    """Helper: create and return a saved Drone with sensible defaults."""
    defaults = dict(
        name=name,
        model=model,
        max_speed=15,
        max_distance_no_load=50,
        slowdown_ratio_per_degree=0.9 / 180,
        min_slowdown_ratio=0.01,
        price_per_cycle=3,
        price_per_kilometer=0.1,
        price_per_hour=0.01,
        max_height=1,
        weight=25,
        max_load=30,
    )
    defaults.update(overrides)
    return Drone.objects.create(**defaults)


def _flat_waypoints(waypoints_nested):
    """Flatten list-of-lists waypoints into a single list of dicts."""
    return [wp for segment in waypoints_nested for wp in segment]


# ---------------------------------------------------------------------------
# FullPipelineTests
# ---------------------------------------------------------------------------


class FullPipelineTests(TestCase):
    """End-to-end tests: field + drone -> get_route -> validate output."""

    def setUp(self):
        self.user = User.objects.create_user(username="testpilot", password="pass1234")
        self.field = Field.objects.create(
            name="TestField",
            owner=self.user,
            points_serialized=json.dumps(FIELD_POINTS),
            road_serialized=json.dumps(ROAD_POINTS),
            holes_serialized=json.dumps([]),
        )
        self.drone = _make_drone()

    # -- 1. Full route generation, no holes ----------------------------------

    def test_full_route_no_holes(self):
        """Create field + drone, call get_route. Grid and waypoints must be
        non-empty; each segment must have >= 3 points (fly_to + coverage +
        fly_back); every waypoint dict must carry the required keys."""
        grid, waypoints, _car_wps, _first_car = get_route(
            car_move=[0.5],
            direction=0,
            start="sw",
            field=deepcopy(FIELD_POINTS),
            grid_step=500,
            road=deepcopy(ROAD_POINTS),
            drones=[self.drone],
            pyproj_transformer=TRANSFORMER,
        )

        # Grid non-empty
        non_empty_lines = [line for line in grid if line]
        self.assertGreater(len(non_empty_lines), 0, "Grid must contain at least one non-empty line")

        # Waypoints non-empty
        self.assertGreater(len(waypoints), 0, "Route must produce at least one waypoint segment")

        # Each segment has at least 3 points (fly_to, coverage point(s), fly_back)
        for idx, segment in enumerate(waypoints):
            self.assertGreaterEqual(
                len(segment),
                3,
                f"Segment {idx} has only {len(segment)} points; expected >= 3",
            )

        # Every waypoint dict has required keys
        for segment in waypoints:
            for wp in segment:
                for key in REQUIRED_WP_KEYS:
                    self.assertIn(
                        key,
                        wp,
                        f"Waypoint missing required key '{key}': {wp}",
                    )

    # -- 2. Different directions produce different costs ---------------------

    def test_different_directions_different_costs(self):
        """direction=0 vs direction=90 should produce different total distances."""
        _, wps_0, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="sw",
            field=deepcopy(FIELD_POINTS),
            grid_step=500,
            road=deepcopy(ROAD_POINTS),
            drones=[self.drone],
            pyproj_transformer=TRANSFORMER,
        )
        _, wps_90, _, _ = get_route(
            car_move=[0.5],
            direction=90,
            start="sw",
            field=deepcopy(FIELD_POINTS),
            grid_step=500,
            road=deepcopy(ROAD_POINTS),
            drones=[self.drone],
            pyproj_transformer=TRANSFORMER,
        )

        def _total_distance(waypoints_nested):
            total = 0
            for seg in waypoints_nested:
                total += waypoints_distance(
                    seg,
                    lat_f=lambda x: x["lat"],
                    lon_f=lambda x: x["lon"],
                )
            return total

        dist_0 = _total_distance(wps_0)
        dist_90 = _total_distance(wps_90)

        # Both routes should traverse something
        self.assertGreater(dist_0, 0, "Direction=0 route distance must be > 0")
        self.assertGreater(dist_90, 0, "Direction=90 route distance must be > 0")
        # Distances must differ for a non-square field
        self.assertNotAlmostEqual(
            dist_0,
            dist_90,
            places=0,
            msg="Routes at direction 0 and 90 should have different total distances",
        )

    # -- 3. Cost calculation pipeline ----------------------------------------

    def test_cost_calculation_pipeline(self):
        """Generate route, compute distance/time/price per drone segment.
        All values must be positive; penalty = 0 when within time limits."""
        _, waypoints, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="sw",
            field=deepcopy(FIELD_POINTS),
            grid_step=500,
            road=deepcopy(ROAD_POINTS),
            drones=[self.drone],
            pyproj_transformer=TRANSFORMER,
        )

        self.assertGreater(len(waypoints), 0)

        for seg_idx, segment in enumerate(waypoints):
            distance = waypoints_distance(
                segment,
                lat_f=lambda x: x["lat"],
                lon_f=lambda x: x["lon"],
            )
            time = waypoints_flight_time(
                segment,
                lat_f=lambda x: x["lat"],
                lon_f=lambda x: x["lon"],
                max_speed_f=lambda x: x["drone"]["max_speed"],
                slowdown_ratio_f=lambda x: x["drone"]["slowdown_ratio_per_degree"],
                min_slowdown_ratio_f=lambda x: x["drone"]["min_slowdown_ratio"],
                spray_on_f=lambda x: x.get("spray_on", False),
            )
            dp = drone_flight_price(segment[0]["drone"], distance / 1000, time)

            self.assertGreater(distance, 0, f"Segment {seg_idx}: distance must be > 0")
            self.assertGreater(time, 0, f"Segment {seg_idx}: flight time must be > 0")
            self.assertGreater(dp, 0, f"Segment {seg_idx}: drone price must be > 0")

            # Penalty should be 0 when time is well within limits
            penalty = flight_penalty(
                time=time,
                borderline_time=1000,
                max_time=2000,
                salary=10,
                drone_price=dp,
                total_grid=100,
                grid_traversed=100,
            )
            self.assertEqual(
                penalty,
                0,
                f"Segment {seg_idx}: penalty should be 0 when time is within limits",
            )

    # -- 4. Multiple truck stops -> more segments ----------------------------

    def test_multiple_truck_stops(self):
        """car_move=[0.25, 0.5, 0.75] should produce more waypoint segments
        than car_move=[0.5]."""
        _, wps_single, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="sw",
            field=deepcopy(FIELD_POINTS),
            grid_step=500,
            road=deepcopy(ROAD_POINTS),
            drones=[self.drone],
            pyproj_transformer=TRANSFORMER,
        )
        _, wps_multi, _, _ = get_route(
            car_move=[0.25, 0.5, 0.75],
            direction=0,
            start="sw",
            field=deepcopy(FIELD_POINTS),
            grid_step=500,
            road=deepcopy(ROAD_POINTS),
            drones=[self.drone],
            pyproj_transformer=TRANSFORMER,
        )

        self.assertGreaterEqual(
            len(wps_multi),
            len(wps_single),
            "More truck stops should produce at least as many waypoint segments",
        )

    # -- 5. Grid density scales with step ------------------------------------

    def test_grid_density_scales_with_step(self):
        """grid_step=200 must produce more grid points than grid_step=500."""
        grid_fine, _, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="sw",
            field=deepcopy(FIELD_POINTS),
            grid_step=200,
            road=deepcopy(ROAD_POINTS),
            drones=[self.drone],
            pyproj_transformer=TRANSFORMER,
        )
        grid_coarse, _, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="sw",
            field=deepcopy(FIELD_POINTS),
            grid_step=500,
            road=deepcopy(ROAD_POINTS),
            drones=[self.drone],
            pyproj_transformer=TRANSFORMER,
        )

        pts_fine = sum(len(line) for line in grid_fine if line)
        pts_coarse = sum(len(line) for line in grid_coarse if line)

        self.assertGreater(
            pts_fine,
            pts_coarse,
            "Smaller grid step must produce more points",
        )

    # -- 6. Waypoints cover the field ----------------------------------------

    def test_waypoints_cover_field(self):
        """All spray_on=True waypoints should have lat/lon within a reasonable
        bounding box of the field (with margin for projection artefacts)."""
        _, waypoints, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="sw",
            field=deepcopy(FIELD_POINTS),
            grid_step=500,
            road=deepcopy(ROAD_POINTS),
            drones=[self.drone],
            pyproj_transformer=TRANSFORMER,
        )

        lons = [p[0] for p in FIELD_POINTS]
        lats = [p[1] for p in FIELD_POINTS]
        margin = 0.02  # ~2 km margin for edge effects / projection

        min_lon, max_lon = min(lons) - margin, max(lons) + margin
        min_lat, max_lat = min(lats) - margin, max(lats) + margin

        spray_count = 0
        for segment in waypoints:
            for wp in segment:
                if wp.get("spray_on"):
                    spray_count += 1
                    self.assertGreaterEqual(
                        wp["lon"],
                        min_lon,
                        f"spray_on waypoint lon {wp['lon']} below min {min_lon}",
                    )
                    self.assertLessEqual(
                        wp["lon"],
                        max_lon,
                        f"spray_on waypoint lon {wp['lon']} above max {max_lon}",
                    )
                    self.assertGreaterEqual(
                        wp["lat"],
                        min_lat,
                        f"spray_on waypoint lat {wp['lat']} below min {min_lat}",
                    )
                    self.assertLessEqual(
                        wp["lat"],
                        max_lat,
                        f"spray_on waypoint lat {wp['lat']} above max {max_lat}",
                    )

        self.assertGreater(spray_count, 0, "Must have at least one spray_on waypoint")

    # -- 7. Multiple drones --------------------------------------------------

    def test_multiple_drones(self):
        """With 2 drones, waypoints should reference both drones (at least
        some segments use each)."""
        drone2 = _make_drone(
            name="TestDrone-2",
            model="DJI-T40",
            max_distance_no_load=30,
        )

        _, waypoints, _, _ = get_route(
            car_move=[0.5],
            direction=0,
            start="sw",
            field=deepcopy(FIELD_POINTS),
            grid_step=500,
            road=deepcopy(ROAD_POINTS),
            drones=[self.drone, drone2],
            pyproj_transformer=TRANSFORMER,
        )

        drone_ids_seen = set()
        for segment in waypoints:
            for wp in segment:
                drone_ids_seen.add(wp["drone"]["id"])

        self.assertIn(
            self.drone.id,
            drone_ids_seen,
            "First drone should appear in waypoints",
        )
        self.assertIn(
            drone2.id,
            drone_ids_seen,
            "Second drone should appear in waypoints",
        )


# ---------------------------------------------------------------------------
# FullPipelineWithHolesTests
# ---------------------------------------------------------------------------


HOLES = [[[76.92, 43.21], [76.93, 43.21], [76.93, 43.22], [76.92, 43.22]]]


class FullPipelineWithHolesTests(TestCase):
    """End-to-end tests with holes (obstacles) in the field."""

    def setUp(self):
        self.user = User.objects.create_user(username="testpilot_holes", password="pass1234")
        self.field = Field.objects.create(
            name="TestFieldHoles",
            owner=self.user,
            points_serialized=json.dumps(FIELD_POINTS),
            road_serialized=json.dumps(ROAD_POINTS),
            holes_serialized=json.dumps(HOLES),
        )
        self.drone = _make_drone(name="HoleDrone", model="DJI-H1")

    # -- 8. Route with holes -------------------------------------------------

    def test_route_with_holes(self):
        """Route with a hole in the middle (simple_holes_traversal=True).
        Route must still generate. No spray_on waypoint should fall inside
        the hole polygon (within reasonable tolerance)."""
        grid, waypoints, _car_wps, _first_car = get_route(
            car_move=[0.5],
            direction=0,
            start="sw",
            field=deepcopy(FIELD_POINTS),
            grid_step=500,
            road=deepcopy(ROAD_POINTS),
            drones=[self.drone],
            pyproj_transformer=TRANSFORMER,
            holes=deepcopy(HOLES),
            simple_holes_traversal=True,
        )

        # Route must generate successfully
        non_empty_lines = [line for line in grid if line]
        self.assertGreater(len(non_empty_lines), 0, "Grid must have non-empty lines even with holes")
        self.assertGreater(len(waypoints), 0, "Must produce waypoint segments even with holes")

        # Build a slightly shrunk hole polygon to avoid false positives at
        # edges due to floating point.
        hole_coords = HOLES[0]
        hole_poly = ShapelyPolygon([(p[0], p[1]) for p in hole_coords])
        # Shrink hole by a small negative buffer so edge points do not fail
        hole_inner = hole_poly.buffer(-0.001)

        for segment in waypoints:
            for wp in segment:
                if wp.get("spray_on"):
                    pt = ShapelyPoint(wp["lon"], wp["lat"])
                    self.assertFalse(
                        hole_inner.contains(pt),
                        f"spray_on waypoint ({wp['lon']}, {wp['lat']}) is inside the hole polygon",
                    )


# ---------------------------------------------------------------------------
# SanityTests - utility function sanity checks
# ---------------------------------------------------------------------------


class SanityTests(TestCase):
    """Low-level sanity checks for utility cost/distance/time functions."""

    def setUp(self):
        self.drone = _make_drone(name="SanityDrone", model="DJI-S1")

    # -- 9. Distance is symmetric --------------------------------------------

    def test_distance_is_symmetric(self):
        """Distance from A to B should approximately equal distance from B to A."""
        path_ab = [
            {"lat": 43.2, "lon": 76.9},
            {"lat": 43.22, "lon": 76.93},
            {"lat": 43.25, "lon": 76.95},
        ]
        path_ba = list(reversed(path_ab))

        dist_ab = waypoints_distance(path_ab, lat_f=lambda x: x["lat"], lon_f=lambda x: x["lon"])
        dist_ba = waypoints_distance(path_ba, lat_f=lambda x: x["lat"], lon_f=lambda x: x["lon"])

        self.assertAlmostEqual(
            dist_ab,
            dist_ba,
            places=2,
            msg="Distance should be symmetric (A->B == B->A)",
        )

    # -- 10. Zero-length path ------------------------------------------------

    def test_zero_length_path(self):
        """A single waypoint should yield distance ~= 0."""
        single = [{"lat": 43.2, "lon": 76.9}]
        dist = waypoints_distance(single, lat_f=lambda x: x["lat"], lon_f=lambda x: x["lon"])
        self.assertAlmostEqual(dist, 0, places=5, msg="Single point -> distance ~ 0")

    # -- 11. Price increases with distance -----------------------------------

    def test_price_increases_with_distance(self):
        """A longer route must cost more than a shorter one."""
        drone_dict = {
            "price_per_cycle": 3,
            "price_per_kilometer": 0.1,
            "price_per_hour": 0.01,
        }
        price_short = drone_flight_price(drone_dict, distance=5, time=0.5)
        price_long = drone_flight_price(drone_dict, distance=50, time=5)

        self.assertGreater(
            price_long,
            price_short,
            "Longer route must be more expensive",
        )

    # -- 12. Penalty explodes past max_time ----------------------------------

    def test_penalty_explodes_past_max_time(self):
        """Penalty at time=100 (way over max) >> penalty at time=3 (borderline)."""
        drone_dict = {
            "price_per_cycle": 3,
            "price_per_kilometer": 0.1,
            "price_per_hour": 0.01,
        }
        dp = drone_flight_price(drone_dict, distance=10, time=1)

        penalty_slight = flight_penalty(
            time=3,
            borderline_time=2,
            max_time=5,
            salary=10,
            drone_price=dp,
            total_grid=100,
            grid_traversed=100,
        )
        penalty_extreme = flight_penalty(
            time=100,
            borderline_time=2,
            max_time=5,
            salary=10,
            drone_price=dp,
            total_grid=100,
            grid_traversed=100,
        )

        self.assertGreater(
            penalty_extreme,
            penalty_slight,
            "Penalty far past max_time must greatly exceed borderline penalty",
        )
        # The exponential blowup should make extreme penalty orders of magnitude larger
        self.assertGreater(
            penalty_extreme,
            penalty_slight * 100,
            "Penalty should be at least 100x worse when time is way past max",
        )

    # -- 13. Round-trip coordinate transformation ----------------------------

    def test_round_trip_coordinates(self):
        """Transform to equidistant and back should match original within
        0.001 degrees."""
        original = [[76.9, 43.2], [76.95, 43.23], [76.92, 43.21]]
        points = deepcopy(original)

        transform_to_equidistant(points)

        # After transforming, values should be in metric (large numbers)
        for pt in points:
            self.assertGreater(
                abs(pt[0]),
                1000,
                "Equidistant projection should produce large metric values",
            )

        transform_to_lat_lon(points)

        # After round-trip, values should be back near the originals
        for orig, recovered in zip(original, points):
            self.assertAlmostEqual(
                orig[0],
                recovered[0],
                places=3,
                msg=f"Longitude round-trip failed: {orig[0]} vs {recovered[0]}",
            )
            self.assertAlmostEqual(
                orig[1],
                recovered[1],
                places=3,
                msg=f"Latitude round-trip failed: {orig[1]} vs {recovered[1]}",
            )
