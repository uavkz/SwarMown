"""
Tests for the REST API endpoints defined in restapp.

Covers: FieldViewSet.create (POST /api/field/)
"""
import json

from django.contrib.auth.models import User
from django.test import TestCase, Client

from mainapp.models import Field


class FieldCreateAPITestCase(TestCase):
    """Tests for the POST /api/field/ endpoint (FieldViewSet.create).

    The view reads data from request.POST (not JSON body), so we send
    data as regular form-encoded POST parameters.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("testuser", password="testpass")
        self.valid_data = {
            "name": "Test Field",
            "points_serialized": "[[50.0, 30.0], [50.1, 30.0], [50.1, 30.1], [50.0, 30.1]]",
            "road_serialized": "[[50.0, 29.9], [50.1, 29.9]]",
        }
        self.api_url = "/api/field/"

    def _login(self):
        self.client.login(username="testuser", password="testpass")

    # ------------------------------------------------------------------
    # 1. Create field - success
    # ------------------------------------------------------------------
    def test_create_field_success(self):
        """POST with valid data and authenticated user returns 200."""
        self._login()
        response = self.client.post(self.api_url, data=self.valid_data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 200)
        self.assertTrue(
            Field.objects.filter(owner=self.user, name="Test Field").exists()
        )

    # ------------------------------------------------------------------
    # 2. Create field - no auth
    # ------------------------------------------------------------------
    def test_create_field_no_auth(self):
        """POST without authentication returns 403."""
        response = self.client.post(self.api_url, data=self.valid_data)
        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------------
    # 3. Create field - missing name
    # ------------------------------------------------------------------
    def test_create_field_missing_name(self):
        """POST without 'name' returns an error response."""
        self._login()
        data = self.valid_data.copy()
        del data["name"]
        response = self.client.post(self.api_url, data=data)
        body = response.json()
        self.assertEqual(body["status"], 500)
        self.assertIn("error", body)

    # ------------------------------------------------------------------
    # 4. Create field - missing points
    # ------------------------------------------------------------------
    def test_create_field_missing_points(self):
        """POST without 'points_serialized' returns an error response."""
        self._login()
        data = self.valid_data.copy()
        del data["points_serialized"]
        response = self.client.post(self.api_url, data=data)
        body = response.json()
        self.assertEqual(body["status"], 500)
        self.assertIn("error", body)

    # ------------------------------------------------------------------
    # 5. Create field - missing road
    # ------------------------------------------------------------------
    def test_create_field_missing_road(self):
        """POST without 'road_serialized' returns an error response."""
        self._login()
        data = self.valid_data.copy()
        del data["road_serialized"]
        response = self.client.post(self.api_url, data=data)
        body = response.json()
        self.assertEqual(body["status"], 500)
        self.assertIn("error", body)

    # ------------------------------------------------------------------
    # 6. Create field - duplicate name
    # ------------------------------------------------------------------
    def test_create_field_duplicate_name(self):
        """Creating a second field with the same name returns an error."""
        self._login()
        # First creation should succeed
        resp1 = self.client.post(self.api_url, data=self.valid_data)
        self.assertEqual(resp1.status_code, 200)

        # Second creation with the same name should fail
        resp2 = self.client.post(self.api_url, data=self.valid_data)
        body = resp2.json()
        self.assertEqual(body["status"], 500)
        self.assertIn("error", body)

    # ------------------------------------------------------------------
    # 7. Create field with holes
    # ------------------------------------------------------------------
    def test_create_field_with_holes(self):
        """Holes with >= 3 points are stored correctly."""
        self._login()
        holes = [
            [[50.02, 30.02], [50.03, 30.02], [50.03, 30.03]],
        ]
        data = self.valid_data.copy()
        data["holes_serialized"] = json.dumps(holes)
        response = self.client.post(self.api_url, data=data)
        self.assertEqual(response.status_code, 200)

        field = Field.objects.get(owner=self.user, name="Test Field")
        stored_holes = json.loads(field.holes_serialized)
        self.assertEqual(len(stored_holes), 1)
        self.assertEqual(stored_holes, holes)

    # ------------------------------------------------------------------
    # 8. Create field filters small holes
    # ------------------------------------------------------------------
    def test_create_field_filters_small_holes(self):
        """Holes with fewer than 3 points are filtered out."""
        self._login()
        holes = [
            [[50.02, 30.02], [50.03, 30.02]],                     # 2 points - too few
            [[50.04, 30.04], [50.05, 30.04], [50.05, 30.05]],     # 3 points - valid
            [[50.06, 30.06]],                                       # 1 point  - too few
        ]
        data = self.valid_data.copy()
        data["holes_serialized"] = json.dumps(holes)
        response = self.client.post(self.api_url, data=data)
        self.assertEqual(response.status_code, 200)

        field = Field.objects.get(owner=self.user, name="Test Field")
        stored_holes = json.loads(field.holes_serialized)
        # Only the hole with 3 points should survive filtering
        self.assertEqual(len(stored_holes), 1)
        self.assertEqual(
            stored_holes[0],
            [[50.04, 30.04], [50.05, 30.04], [50.05, 30.05]],
        )
