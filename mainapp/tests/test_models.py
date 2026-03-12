import json

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from mainapp.models import Drone, Field, Mission, Waypoint

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_user(username="testuser"):
    return User.objects.create_user(username=username, password="testpass")


def _create_field(owner, name="Test Field"):
    return Field.objects.create(
        owner=owner,
        name=name,
        points_serialized="[[50.0, 30.0], [50.1, 30.0], [50.1, 30.1], [50.0, 30.1]]",
        road_serialized="[[50.0, 29.9], [50.1, 29.9]]",
        holes_serialized="[]",
    )


def _create_drone(name="Drone1", model="M1"):
    return Drone.objects.create(
        name=name,
        model=model,
        max_distance_no_load=10,
        weight=5,
        max_load=2,
    )


def _create_mission(owner, field, name="Test Mission", mission_type=1):
    return Mission.objects.create(
        owner=owner,
        name=name,
        field=field,
        type=mission_type,
    )


def _create_waypoint(drone, lat=50.0, lon=30.0, height=10, speed=15, acceleration=0, index=0, spray_on=False):
    return Waypoint.objects.create(
        drone=drone,
        lat=lat,
        lon=lon,
        height=height,
        speed=speed,
        acceleration=acceleration,
        index=index,
        spray_on=spray_on,
    )


# ===========================================================================
# 1. Creation smoke tests
# ===========================================================================


class FieldCreationTests(TestCase):
    """Verify that a Field can be created, saved, and retrieved."""

    def test_create_and_retrieve(self):
        user = _create_user()
        field = _create_field(user)
        fetched = Field.objects.get(pk=field.pk)
        self.assertEqual(fetched.name, "Test Field")
        self.assertEqual(fetched.owner, user)

    def test_str(self):
        user = _create_user()
        field = _create_field(user, name="Alpha")
        self.assertEqual(str(field), "Alpha")


class MissionCreationTests(TestCase):
    """Verify that a Mission can be created, saved, and retrieved."""

    def test_create_and_retrieve(self):
        user = _create_user()
        field = _create_field(user)
        mission = _create_mission(user, field)
        fetched = Mission.objects.get(pk=mission.pk)
        self.assertEqual(fetched.name, "Test Mission")
        self.assertEqual(fetched.owner, user)
        self.assertEqual(fetched.field, field)

    def test_str_contains_name_and_type(self):
        user = _create_user()
        field = _create_field(user)
        mission = _create_mission(user, field, mission_type=1)
        s = str(mission)
        self.assertIn("Test Mission", s)

    def test_datetime_auto_now_add(self):
        user = _create_user()
        field = _create_field(user)
        mission = _create_mission(user, field)
        self.assertIsNotNone(mission.datetime)


class DroneCreationTests(TestCase):
    """Verify that a Drone can be created, saved, and retrieved."""

    def test_create_and_retrieve(self):
        drone = _create_drone()
        fetched = Drone.objects.get(pk=drone.pk)
        self.assertEqual(fetched.name, "Drone1")
        self.assertEqual(fetched.model, "M1")

    def test_str(self):
        drone = _create_drone(name="X1", model="ProMax")
        self.assertEqual(str(drone), "X1 (ProMax)")


class WaypointCreationTests(TestCase):
    """Verify that a Waypoint can be created, saved, and retrieved."""

    def test_create_and_retrieve(self):
        drone = _create_drone()
        wp = _create_waypoint(drone)
        fetched = Waypoint.objects.get(pk=wp.pk)
        self.assertEqual(fetched.lat, 50.0)
        self.assertEqual(fetched.lon, 30.0)
        self.assertEqual(fetched.drone, drone)


# ===========================================================================
# 2. Default values
# ===========================================================================


class DefaultValuesTests(TestCase):
    """Verify default values declared on model fields."""

    def test_mission_defaults(self):
        user = _create_user()
        field = _create_field(user)
        mission = _create_mission(user, field)

        self.assertEqual(mission.status, 0)
        self.assertEqual(mission.grid_step, 100)
        self.assertEqual(mission.start_price, 3)
        self.assertEqual(mission.hourly_price, 10)
        self.assertEqual(mission.current_waypoints_status, 0)

    def test_drone_defaults(self):
        drone = _create_drone()
        self.assertEqual(drone.max_speed, 15)
        self.assertAlmostEqual(drone.slowdown_ratio_per_degree, 0.9 / 180)
        self.assertEqual(drone.min_slowdown_ratio, 0.01)
        self.assertEqual(drone.price_per_cycle, 3)
        self.assertEqual(drone.price_per_kilometer, 0.1)
        self.assertEqual(drone.price_per_hour, 0.01)
        self.assertEqual(drone.max_height, 1)

    def test_waypoint_status_default(self):
        drone = _create_drone()
        wp = _create_waypoint(drone)
        self.assertEqual(wp.status, 0)


# ===========================================================================
# 3. Relationships
# ===========================================================================


class FieldMissionRelationshipTests(TestCase):
    """Field -> Mission FK; deleting a Field cascades to its Missions."""

    def test_mission_links_to_field(self):
        user = _create_user()
        field = _create_field(user)
        mission = _create_mission(user, field)
        self.assertEqual(mission.field_id, field.pk)

    def test_delete_field_cascades_to_missions(self):
        user = _create_user()
        field = _create_field(user)
        _create_mission(user, field)
        field.delete()
        self.assertEqual(Mission.objects.count(), 0)


class MissionDroneM2MTests(TestCase):
    """Mission <-> Drone many-to-many relationship."""

    def test_add_drones_to_mission(self):
        user = _create_user()
        field = _create_field(user)
        mission = _create_mission(user, field)

        d1 = _create_drone("A", "M1")
        d2 = _create_drone("B", "M2")
        mission.drones.add(d1, d2)

        self.assertEqual(mission.drones.count(), 2)
        self.assertIn(d1, mission.drones.all())
        self.assertIn(d2, mission.drones.all())

    def test_remove_drone_from_mission(self):
        user = _create_user()
        field = _create_field(user)
        mission = _create_mission(user, field)
        drone = _create_drone()
        mission.drones.add(drone)
        mission.drones.remove(drone)
        self.assertEqual(mission.drones.count(), 0)

    def test_clear_drones(self):
        user = _create_user()
        field = _create_field(user)
        mission = _create_mission(user, field)
        d1 = _create_drone("D1", "M1")
        d2 = _create_drone("D2", "M2")
        mission.drones.add(d1, d2)
        mission.drones.clear()
        self.assertEqual(mission.drones.count(), 0)
        # Drones themselves still exist.
        self.assertEqual(Drone.objects.count(), 2)


class MissionWaypointM2MTests(TestCase):
    """Mission <-> Waypoint many-to-many (current_waypoints & waypoints_history)."""

    def test_add_current_waypoints(self):
        user = _create_user()
        field = _create_field(user)
        mission = _create_mission(user, field)
        drone = _create_drone()

        wp1 = _create_waypoint(drone, index=0)
        wp2 = _create_waypoint(drone, lat=50.1, lon=30.1, index=1)
        mission.current_waypoints.add(wp1, wp2)

        self.assertEqual(mission.current_waypoints.count(), 2)

    def test_add_waypoints_history(self):
        user = _create_user()
        field = _create_field(user)
        mission = _create_mission(user, field)
        drone = _create_drone()

        wp = _create_waypoint(drone)
        mission.waypoints_history.add(wp)
        self.assertEqual(mission.waypoints_history.count(), 1)

    def test_waypoint_reverse_relation(self):
        user = _create_user()
        field = _create_field(user)
        mission = _create_mission(user, field)
        drone = _create_drone()
        wp = _create_waypoint(drone)
        mission.current_waypoints.add(wp)

        # Waypoint -> Mission via related_name 'mission'
        self.assertIn(mission, wp.mission.all())


class DroneWaypointRelationshipTests(TestCase):
    """Drone -> Waypoint FK; deleting a Drone cascades to its Waypoints."""

    def test_waypoint_links_to_drone(self):
        drone = _create_drone()
        wp = _create_waypoint(drone)
        self.assertEqual(wp.drone, drone)

    def test_delete_drone_cascades_to_waypoints(self):
        drone = _create_drone()
        _create_waypoint(drone)
        _create_waypoint(drone, lat=51, lon=31, index=1)
        drone.delete()
        self.assertEqual(Waypoint.objects.count(), 0)


# ===========================================================================
# 4. Unique constraints
# ===========================================================================


class FieldUniqueConstraintTests(TestCase):
    """UniqueConstraint on (owner, name) for Field."""

    def test_duplicate_name_same_owner_raises(self):
        user = _create_user()
        _create_field(user, name="Shared")
        with self.assertRaises(IntegrityError):
            _create_field(user, name="Shared")

    def test_same_name_different_owner_ok(self):
        u1 = _create_user("user1")
        u2 = _create_user("user2")
        _create_field(u1, name="Shared")
        f2 = _create_field(u2, name="Shared")
        self.assertIsNotNone(f2.pk)

    def test_different_name_same_owner_ok(self):
        user = _create_user()
        _create_field(user, name="FieldA")
        f2 = _create_field(user, name="FieldB")
        self.assertIsNotNone(f2.pk)


class MissionUniqueConstraintTests(TestCase):
    """UniqueConstraint on (owner, name) for Mission."""

    def test_duplicate_name_same_owner_raises(self):
        user = _create_user()
        field = _create_field(user)
        _create_mission(user, field, name="Alpha")
        with self.assertRaises(IntegrityError):
            _create_mission(user, field, name="Alpha")

    def test_same_name_different_owner_ok(self):
        u1 = _create_user("user1")
        u2 = _create_user("user2")
        f1 = _create_field(u1, name="F1")
        f2 = _create_field(u2, name="F2")
        _create_mission(u1, f1, name="Alpha")
        m2 = _create_mission(u2, f2, name="Alpha")
        self.assertIsNotNone(m2.pk)


class DroneUniqueTogetherTests(TestCase):
    """unique_together on (name, model) for Drone."""

    def test_duplicate_name_and_model_raises(self):
        _create_drone("X1", "Pro")
        with self.assertRaises(IntegrityError):
            _create_drone("X1", "Pro")

    def test_same_name_different_model_ok(self):
        _create_drone("X1", "Pro")
        d2 = _create_drone("X1", "Lite")
        self.assertIsNotNone(d2.pk)

    def test_different_name_same_model_ok(self):
        _create_drone("X1", "Pro")
        d2 = _create_drone("X2", "Pro")
        self.assertIsNotNone(d2.pk)


# ===========================================================================
# 5. Properties
# ===========================================================================


class MissionPropertyTests(TestCase):
    """Test verbose properties on Mission."""

    def setUp(self):
        self.user = _create_user()
        self.field = _create_field(self.user)

    def test_status_verbose_default(self):
        mission = _create_mission(self.user, self.field)
        # status=0 -> "Не запущен"  # noqa: RUF003
        self.assertEqual(mission.status_verbose, "Не запущен")

    def test_status_verbose_all_values(self):
        expected = {
            -2: "Критическая ошибка",
            -1: "Отмена",
            0: "Не запущен",
            1: "В ожидании",
            2: "В работе",
            3: "Завершен",
        }
        for code, label in expected.items():
            mission = _create_mission(self.user, self.field, name=f"m_{code}")
            mission.status = code
            mission.save()
            self.assertEqual(mission.status_verbose, label)

    def test_type_verbose(self):
        expected = {
            1: "Опрыскивание",
            2: "Аеро-фото-съемка",
            3: "Детальная съемка",
        }
        for code, label in expected.items():
            mission = _create_mission(self.user, self.field, name=f"t_{code}", mission_type=code)
            self.assertEqual(mission.type_verbose, label)

    def test_current_waypoints_status_verbose(self):
        mission = _create_mission(self.user, self.field)
        expected = {
            0: "Не рассчитано",
            1: "В процессе расчета",
            2: "Готово",
        }
        for code, label in expected.items():
            mission.current_waypoints_status = code
            mission.save()
            self.assertEqual(mission.current_waypoints_status_verbose, label)

    def test_drones_verbose_empty(self):
        mission = _create_mission(self.user, self.field)
        self.assertEqual(mission.drones_verbose, "")

    def test_drones_verbose_multiple(self):
        mission = _create_mission(self.user, self.field)
        d1 = _create_drone("Alpha", "M1")
        d2 = _create_drone("Beta", "M2")
        mission.drones.add(d1, d2)
        verbose = mission.drones_verbose
        self.assertIn("Alpha (M1)", verbose)
        self.assertIn("Beta (M2)", verbose)

    def test_simulated_distance_no_waypoints(self):
        mission = _create_mission(self.user, self.field)
        self.assertEqual(mission.simulated_distance, 0)

    def test_simulated_distance_with_waypoints(self):
        mission = _create_mission(self.user, self.field)
        drone = _create_drone()
        wp1 = _create_waypoint(drone, lat=50.0, lon=30.0, index=0)
        wp2 = _create_waypoint(drone, lat=50.1, lon=30.0, index=1)
        mission.current_waypoints.add(wp1, wp2)
        dist = mission.simulated_distance
        # Two points ~11.1 km apart; distance should be positive.
        self.assertGreater(dist, 0)

    def test_simulated_flight_time_no_waypoints(self):
        mission = _create_mission(self.user, self.field)
        self.assertEqual(mission.simulated_flight_time, 0)

    def test_simulated_flight_time_with_waypoints(self):
        mission = _create_mission(self.user, self.field)
        drone = _create_drone()
        wp1 = _create_waypoint(drone, lat=50.0, lon=30.0, index=0)
        wp2 = _create_waypoint(drone, lat=50.1, lon=30.0, index=1)
        mission.current_waypoints.add(wp1, wp2)
        t = mission.simulated_flight_time
        self.assertGreater(t, 0)

    def test_history_distance_with_waypoints(self):
        mission = _create_mission(self.user, self.field)
        drone = _create_drone()
        wp1 = _create_waypoint(drone, lat=50.0, lon=30.0, index=0)
        wp2 = _create_waypoint(drone, lat=50.05, lon=30.05, index=1)
        mission.waypoints_history.add(wp1, wp2)
        self.assertGreater(mission.history_distance, 0)

    def test_history_flight_time_with_waypoints(self):
        mission = _create_mission(self.user, self.field)
        drone = _create_drone()
        wp1 = _create_waypoint(drone, lat=50.0, lon=30.0, index=0)
        wp2 = _create_waypoint(drone, lat=50.05, lon=30.05, index=1)
        mission.waypoints_history.add(wp1, wp2)
        self.assertGreater(mission.history_flight_time, 0)


class WaypointPropertyTests(TestCase):
    """Test verbose properties on Waypoint."""

    def test_status_verbose_default(self):
        drone = _create_drone()
        wp = _create_waypoint(drone)
        self.assertEqual(wp.status_verbose, "Не начат")

    def test_status_verbose_all_values(self):
        drone = _create_drone()
        expected = {
            -1: "История",
            0: "Не начат",
            1: "В процессе",
            2: "Завершен",
        }
        for code, label in expected.items():
            wp = _create_waypoint(drone, lat=50 + code, lon=30 + code, index=code + 2)
            wp.status = code
            wp.save()
            self.assertEqual(wp.status_verbose, label)


# ===========================================================================
# 6. Cascade deletes
# ===========================================================================


class CascadeDeleteTests(TestCase):
    """Deleting a User should cascade to Fields and Missions."""

    def test_delete_user_cascades_to_fields(self):
        user = _create_user()
        _create_field(user, name="F1")
        _create_field(user, name="F2")
        self.assertEqual(Field.objects.count(), 2)
        user.delete()
        self.assertEqual(Field.objects.count(), 0)

    def test_delete_user_cascades_to_missions(self):
        user = _create_user()
        field = _create_field(user)
        _create_mission(user, field, name="M1")
        _create_mission(user, field, name="M2")
        self.assertEqual(Mission.objects.count(), 2)
        user.delete()
        self.assertEqual(Mission.objects.count(), 0)

    def test_delete_user_cascades_fields_and_missions(self):
        user = _create_user()
        field = _create_field(user)
        _create_mission(user, field)
        user.delete()
        self.assertEqual(Field.objects.count(), 0)
        self.assertEqual(Mission.objects.count(), 0)

    def test_delete_drone_cascades_to_waypoints(self):
        drone = _create_drone()
        _create_waypoint(drone, index=0)
        _create_waypoint(drone, lat=51, lon=31, index=1)
        self.assertEqual(Waypoint.objects.count(), 2)
        drone.delete()
        self.assertEqual(Waypoint.objects.count(), 0)

    def test_delete_field_cascades_to_mission(self):
        user = _create_user()
        field = _create_field(user)
        _create_mission(user, field)
        self.assertEqual(Mission.objects.count(), 1)
        field.delete()
        self.assertEqual(Mission.objects.count(), 0)

    def test_deleting_drone_does_not_delete_mission(self):
        """Drones are M2M with Mission; removing a Drone should not delete the Mission."""
        user = _create_user()
        field = _create_field(user)
        mission = _create_mission(user, field)
        drone = _create_drone()
        mission.drones.add(drone)
        drone.delete()
        self.assertEqual(Mission.objects.count(), 1)
        mission.refresh_from_db()
        self.assertEqual(mission.drones.count(), 0)


# ===========================================================================
# 7. JSON serialized fields
# ===========================================================================


class FieldJsonSerializationTests(TestCase):
    """Ensure that JSON-serialized text fields store and retrieve valid JSON."""

    def test_points_serialized_round_trip(self):
        user = _create_user()
        coords = [[50.0, 30.0], [50.1, 30.0], [50.1, 30.1], [50.0, 30.1]]
        field = Field.objects.create(
            owner=user,
            name="JSON Test",
            points_serialized=json.dumps(coords),
            road_serialized="[]",
            holes_serialized="[]",
        )
        fetched = Field.objects.get(pk=field.pk)
        loaded = json.loads(fetched.points_serialized)
        self.assertEqual(loaded, coords)

    def test_holes_serialized_empty_list(self):
        user = _create_user()
        field = _create_field(user)
        loaded = json.loads(field.holes_serialized)
        self.assertEqual(loaded, [])

    def test_holes_serialized_with_data(self):
        user = _create_user()
        holes = [
            [[50.01, 30.01], [50.02, 30.01], [50.02, 30.02], [50.01, 30.02]],
            [[50.05, 30.05], [50.06, 30.05], [50.06, 30.06]],
        ]
        field = Field.objects.create(
            owner=user,
            name="Holey",
            points_serialized="[[50.0, 30.0]]",
            road_serialized="[]",
            holes_serialized=json.dumps(holes),
        )
        fetched = Field.objects.get(pk=field.pk)
        loaded = json.loads(fetched.holes_serialized)
        self.assertEqual(loaded, holes)

    def test_road_serialized_round_trip(self):
        user = _create_user()
        road = [[50.0, 29.9], [50.1, 29.9]]
        field = _create_field(user)
        fetched = Field.objects.get(pk=field.pk)
        loaded = json.loads(fetched.road_serialized)
        self.assertEqual(loaded, road)

    def test_points_serialized_complex_polygon(self):
        user = _create_user()
        coords = [
            [43.27038611295692, 76.7296543207424],
            [43.14601796133043, 77.03074836368798],
            [43.0, 76.5],
        ]
        field = Field.objects.create(
            owner=user,
            name="Complex Poly",
            points_serialized=json.dumps(coords),
            road_serialized="[]",
            holes_serialized="[]",
        )
        loaded = json.loads(Field.objects.get(pk=field.pk).points_serialized)
        self.assertEqual(loaded, coords)


# ===========================================================================
# 8. Edge cases
# ===========================================================================


class FieldEdgeCaseTests(TestCase):
    """Edge-case scenarios for Field."""

    def test_empty_name(self):
        user = _create_user()
        field = Field.objects.create(
            owner=user,
            name="",
            points_serialized="[]",
            road_serialized="[]",
            holes_serialized="[]",
        )
        self.assertEqual(field.name, "")

    def test_very_long_name(self):
        user = _create_user()
        long_name = "A" * 251  # max_length is 251
        field = Field.objects.create(
            owner=user,
            name=long_name,
            points_serialized="[]",
            road_serialized="[]",
            holes_serialized="[]",
        )
        self.assertEqual(len(field.name), 251)

    def test_owner_null(self):
        """Field.owner is nullable; a field without an owner should be fine."""
        field = Field.objects.create(
            owner=None,
            name="Orphan",
            points_serialized="[]",
            road_serialized="[]",
            holes_serialized="[]",
        )
        self.assertIsNone(field.owner)


class MissionEdgeCaseTests(TestCase):
    """Edge-case scenarios for Mission."""

    def test_null_description(self):
        user = _create_user()
        field = _create_field(user)
        mission = Mission.objects.create(
            owner=user,
            name="NoDesc",
            field=field,
            type=1,
            description=None,
        )
        self.assertIsNone(mission.description)

    def test_blank_description(self):
        user = _create_user()
        field = _create_field(user)
        mission = Mission.objects.create(
            owner=user,
            name="BlankDesc",
            field=field,
            type=1,
            description="",
        )
        self.assertEqual(mission.description, "")

    def test_empty_name(self):
        user = _create_user()
        field = _create_field(user)
        mission = Mission.objects.create(
            owner=user,
            name="",
            field=field,
            type=1,
        )
        self.assertEqual(mission.name, "")

    def test_very_long_name(self):
        user = _create_user()
        field = _create_field(user)
        long_name = "B" * 250  # max_length is 250
        mission = Mission.objects.create(
            owner=user,
            name=long_name,
            field=field,
            type=1,
        )
        self.assertEqual(len(mission.name), 250)

    def test_owner_null(self):
        """Mission.owner is nullable."""
        user = _create_user()
        field = _create_field(user)
        mission = Mission.objects.create(
            owner=None,
            name="OrphanMission",
            field=field,
            type=2,
        )
        self.assertIsNone(mission.owner)

    def test_negative_status(self):
        user = _create_user()
        field = _create_field(user)
        mission = Mission.objects.create(
            owner=user,
            name="CritErr",
            field=field,
            type=1,
            status=-2,
        )
        self.assertEqual(mission.status, -2)
        self.assertEqual(mission.status_verbose, "Критическая ошибка")

    def test_custom_prices(self):
        user = _create_user()
        field = _create_field(user)
        mission = Mission.objects.create(
            owner=user,
            name="Expensive",
            field=field,
            type=1,
            start_price=99.99,
            hourly_price=500.0,
            grid_step=50.5,
        )
        self.assertEqual(mission.start_price, 99.99)
        self.assertEqual(mission.hourly_price, 500.0)
        self.assertEqual(mission.grid_step, 50.5)


class DroneEdgeCaseTests(TestCase):
    """Edge-case scenarios for Drone."""

    def test_custom_defaults_override(self):
        drone = Drone.objects.create(
            name="Custom",
            model="CModel",
            max_speed=25,
            max_distance_no_load=50,
            slowdown_ratio_per_degree=0.005,
            min_slowdown_ratio=0.02,
            price_per_cycle=10,
            price_per_kilometer=0.5,
            price_per_hour=0.1,
            max_height=5,
            weight=10,
            max_load=20,
        )
        self.assertEqual(drone.max_speed, 25)
        self.assertEqual(drone.max_distance_no_load, 50)
        self.assertEqual(drone.slowdown_ratio_per_degree, 0.005)
        self.assertEqual(drone.min_slowdown_ratio, 0.02)
        self.assertEqual(drone.price_per_cycle, 10)
        self.assertEqual(drone.price_per_kilometer, 0.5)
        self.assertEqual(drone.price_per_hour, 0.1)
        self.assertEqual(drone.max_height, 5)
        self.assertEqual(drone.weight, 10)
        self.assertEqual(drone.max_load, 20)


class WaypointEdgeCaseTests(TestCase):
    """Edge-case scenarios for Waypoint."""

    def test_spray_on_null(self):
        drone = _create_drone()
        wp = Waypoint.objects.create(
            drone=drone,
            lat=50.0,
            lon=30.0,
            height=10,
            speed=15,
            acceleration=0,
            spray_on=None,
        )
        self.assertIsNone(wp.spray_on)

    def test_spray_on_true(self):
        drone = _create_drone()
        wp = _create_waypoint(drone, spray_on=True)
        self.assertTrue(wp.spray_on)

    def test_spray_on_false(self):
        drone = _create_drone()
        wp = _create_waypoint(drone, spray_on=False)
        self.assertFalse(wp.spray_on)

    def test_index_null(self):
        drone = _create_drone()
        wp = Waypoint.objects.create(
            drone=drone,
            lat=50.0,
            lon=30.0,
            height=10,
            speed=15,
            acceleration=0,
            index=None,
        )
        self.assertIsNone(wp.index)

    def test_datetime_null(self):
        drone = _create_drone()
        wp = Waypoint.objects.create(
            drone=drone,
            lat=50.0,
            lon=30.0,
            height=10,
            speed=15,
            acceleration=0,
        )
        self.assertIsNone(wp.datetime)

    def test_datetime_set(self):
        drone = _create_drone()
        now = timezone.now()
        wp = Waypoint.objects.create(
            drone=drone,
            lat=50.0,
            lon=30.0,
            height=10,
            speed=15,
            acceleration=0,
            datetime=now,
        )
        self.assertEqual(wp.datetime, now)


# ===========================================================================
# 9. User reverse relations
# ===========================================================================


class UserReverseRelationTests(TestCase):
    """Verify related_name accessors on User."""

    def test_user_fields_reverse(self):
        user = _create_user()
        _create_field(user, "F1")
        _create_field(user, "F2")
        self.assertEqual(user.fields.count(), 2)

    def test_user_missions_reverse(self):
        user = _create_user()
        field = _create_field(user)
        _create_mission(user, field, "M1")
        _create_mission(user, field, "M2")
        self.assertEqual(user.missions.count(), 2)
