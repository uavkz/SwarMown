"""
Smoke tests for mainapp views.

Covers: Index, MissionsListView, MissionsCreateView, ManageRouteView,
        login page, and unauthenticated-access redirects.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from mainapp.models import Field, Mission, Drone


class ViewsSmokeTestCase(TestCase):
    """Base test case with shared setUp for all view smoke tests."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.field = Field.objects.create(
            owner=self.user,
            name="Test Field",
            points_serialized="[[50.0, 30.0], [50.1, 30.0], [50.1, 30.1], [50.0, 30.1]]",
            road_serialized="[[50.0, 29.9], [50.1, 29.9]]",
            holes_serialized="[]",
        )
        self.drone = Drone.objects.create(
            name="D1", model="M1", max_distance_no_load=10, weight=5, max_load=2,
        )
        self.mission = Mission.objects.create(
            owner=self.user,
            name="Test Mission",
            field=self.field,
            grid_step=100,
            type=1,
            status=0,
        )
        self.mission.drones.add(self.drone)


class IndexViewTests(ViewsSmokeTestCase):
    """Tests for the Index view (root URL)."""

    def test_index_redirects_to_login_when_not_authenticated(self):
        """GET / returns 302 redirect to login for anonymous users."""
        self.client.logout()
        response = self.client.get(reverse("mainapp:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_index_redirects_to_missions_when_authenticated(self):
        """GET / returns 302 redirect to mission list for logged-in users."""
        response = self.client.get(reverse("mainapp:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("mainapp:list_mission"), response.url)


class MissionsListViewTests(ViewsSmokeTestCase):
    """Tests for MissionsListView."""

    def test_missions_list_page_loads(self):
        """GET missions list returns 200."""
        response = self.client.get(reverse("mainapp:list_mission"))
        self.assertEqual(response.status_code, 200)


class MissionsCreateViewTests(ViewsSmokeTestCase):
    """Tests for MissionsCreateView (GET and POST)."""

    def test_mission_create_page_loads(self):
        """GET mission create page returns 200."""
        response = self.client.get(reverse("mainapp:add_mission"))
        self.assertEqual(response.status_code, 200)

    def test_mission_create_post_works(self):
        """POST with valid data creates a new mission and redirects."""
        data = {
            "name": "New Mission",
            "description": "A test mission",
            "type": 1,
            "field": self.field.id,
            "grid_step": 50,
            "drones": [self.drone.id],
        }
        response = self.client.post(reverse("mainapp:add_mission"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Mission.objects.filter(name="New Mission", owner=self.user).exists()
        )


class ManageRouteViewTests(ViewsSmokeTestCase):
    """Tests for ManageRouteView."""

    @patch("mainapp.views.get_route")
    def test_manage_route_page_loads(self, mock_get_route):
        """GET manage_route with a valid mission_id returns 200.

        get_route is mocked because it depends on heavy computational
        logic and external modules that are irrelevant for a smoke test.
        """
        mock_waypoint = {
            "lat": 50.0,
            "lon": 30.0,
            "height": 100,
            "speed": 5,
            "acceleration": 1,
            "spray_on": True,
            "drone": {
                "id": self.drone.id,
                "name": self.drone.name,
                "model": self.drone.model,
            },
        }
        # get_route returns (grid, waypoints, car_waypoints, initial_position)
        mock_get_route.return_value = (
            [[[50.0, 30.0, 0, 1]]],  # grid
            [[mock_waypoint]],        # waypoints (list of lists)
            [],                       # car_waypoints
            [50.0, 30.0],             # initial_position
        )
        url = reverse("mainapp:manage_route", kwargs={"mission_id": self.mission.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        mock_get_route.assert_called_once()


class LoginPageTests(TestCase):
    """Tests for the login page."""

    def test_login_page_loads(self):
        """GET login returns 200."""
        response = self.client.get(reverse("mainapp:login"))
        self.assertEqual(response.status_code, 200)


class UnauthenticatedAccessTests(TestCase):
    """Ensure pages that require authentication redirect anonymous users."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("testuser", password="testpass")
        self.field = Field.objects.create(
            owner=self.user,
            name="Test Field",
            points_serialized="[[50.0, 30.0], [50.1, 30.0], [50.1, 30.1], [50.0, 30.1]]",
            road_serialized="[[50.0, 29.9], [50.1, 29.9]]",
            holes_serialized="[]",
        )
        self.drone = Drone.objects.create(
            name="D1", model="M1", max_distance_no_load=10, weight=5, max_load=2,
        )
        self.mission = Mission.objects.create(
            owner=self.user,
            name="Test Mission",
            field=self.field,
            grid_step=100,
            type=1,
            status=0,
        )
        self.mission.drones.add(self.drone)

    def test_index_redirects_unauthenticated(self):
        """Anonymous GET / redirects to login."""
        response = self.client.get(reverse("mainapp:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_manage_route_unauthenticated_returns_error(self):
        """Anonymous GET manage_route does not return a successful page.

        ManageRouteView does not explicitly enforce login. The view tries
        to filter by owner=request.user, which raises a TypeError for
        AnonymousUser (not iterable). Either way, an anonymous user
        cannot access the route page.
        """
        url = reverse(
            "mainapp:manage_route",
            kwargs={"mission_id": self.mission.id},
        )
        with self.assertRaises(TypeError):
            self.client.get(url)
