from django.test import TestCase

from mainapp.utils_mavlink import create_plan_file


class CreatePlanFileTests(TestCase):
    """Tests for create_plan_file() in utils_mavlink."""

    def setUp(self):
        self.waypoints = [[50.0, 30.0], [50.001, 30.001], [50.002, 30.002]]

    # 1. Smoke test
    def test_smoke_returns_dict(self):
        """Calling create_plan_file with simple waypoints returns a dict."""
        result = create_plan_file(self.waypoints, drone_id=1)
        self.assertIsInstance(result, dict)

    # 2. Structure - top-level keys
    def test_structure_has_required_keys(self):
        """Result contains all required top-level keys."""
        result = create_plan_file(self.waypoints, drone_id=1)
        expected_keys = {
            "fileType", "geoFence", "groundStation",
            "mission", "rallyPoints", "version",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    # 3. Mission items count equals number of waypoints
    def test_mission_items_count_equals_waypoints(self):
        """Number of mission items equals the number of input waypoints."""
        result = create_plan_file(self.waypoints, drone_id=1)
        items = result["mission"]["items"]
        self.assertEqual(len(items), len(self.waypoints))

    # 4. First item is home - command=530, frame=2
    def test_first_item_is_home(self):
        """First mission item has command=530 (home) and frame=2."""
        result = create_plan_file(self.waypoints, drone_id=1)
        first_item = result["mission"]["items"][0]
        self.assertEqual(first_item["command"], 530)
        self.assertEqual(first_item["frame"], 2)

    # 5. Second item is takeoff - command=22
    def test_second_item_is_takeoff(self):
        """Second mission item has command=22 (takeoff)."""
        result = create_plan_file(self.waypoints, drone_id=1)
        second_item = result["mission"]["items"][1]
        self.assertEqual(second_item["command"], 22)

    # 6. Regular items (index > 1) - command=16, frame=3
    def test_regular_items_command_and_frame(self):
        """Items after the second one have command=16 and frame=3."""
        result = create_plan_file(self.waypoints, drone_id=1)
        items = result["mission"]["items"]
        for idx in range(2, len(items)):
            with self.subTest(index=idx):
                self.assertEqual(items[idx]["command"], 16)
                self.assertEqual(items[idx]["frame"], 3)

    # 7. Planned home position matches first waypoint coords
    def test_planned_home_position(self):
        """plannedHomePosition uses the first waypoint's lat and lon."""
        result = create_plan_file(self.waypoints, drone_id=1, altitude_world=855)
        home = result["mission"]["plannedHomePosition"]
        self.assertEqual(home[0], self.waypoints[0][0])
        self.assertEqual(home[1], self.waypoints[0][1])
        self.assertEqual(home[2], 855)

    # 8. Ground station equals "QGroundControl"
    def test_ground_station(self):
        """groundStation value is 'QGroundControl'."""
        result = create_plan_file(self.waypoints, drone_id=1)
        self.assertEqual(result["groundStation"], "QGroundControl")

    # 9. Vehicle type equals 2 (quadcopter)
    def test_vehicle_type(self):
        """vehicleType is 2 (quadcopter)."""
        result = create_plan_file(self.waypoints, drone_id=1)
        self.assertEqual(result["mission"]["vehicleType"], 2)

    # 10. Single waypoint works without crash
    def test_single_waypoint(self):
        """create_plan_file works with a single waypoint without crashing."""
        single = [[50.0, 30.0]]
        result = create_plan_file(single, drone_id=1)
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result["mission"]["items"]), 1)
