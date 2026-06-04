"""Tests for the optimizer's AgroScope route export (scripts.ga_common, US-3).

build_optimal_agroscope_plan reconstructs the GA's best route and wraps it in a
MAVLink plan with an agroScopeMeta block — but only for fields imported from an
AgroScope KML.
"""

import json

from django.test import TestCase
from pyproj import Transformer

from mainapp.models import Drone, Field, Mission
from scripts.ga_common import build_optimal_agroscope_plan, load_mission


def _transformer():
    return Transformer.from_crs("epsg:4087", "epsg:4326", always_xy=True)


class OptimizerAgroscopeExportTests(TestCase):
    def setUp(self):
        # Small square field with a road along the southern edge ([lat, lon] in DB).
        self.field = Field.objects.create(
            name="Зона 1",
            points_serialized=json.dumps([[50.0, 82.0], [50.0, 82.01], [50.01, 82.01], [50.01, 82.0]]),
            road_serialized=json.dumps([[49.999, 82.0], [49.999, 82.01]]),
            holes_serialized="[]",
            agroscope_meta_serialized=json.dumps(
                {"task_id": "TASK-2026-053", "task_number": "53", "zone_id": "1", "zone_name": "Зона 1"}
            ),
        )
        self.drone = Drone.objects.create(name="Tello", model="Tello", max_distance_no_load=6.28, weight=1, max_load=1)
        self.mission = Mission.objects.create(name="M", field=self.field, grid_step=80, type=1, status=0)
        self.mission.drones.add(self.drone)
        self.iterations = [{"best_ind": [0.0, "ne", [0], [0.5]]}]

    def test_emits_plan_with_agroscope_meta(self):
        md = load_mission(self.mission.id)
        plan = build_optimal_agroscope_plan(
            md, self.iterations, _transformer(), simple_holes_traversal=True, route_generated_at="2026-06-04T00:00:00Z"
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan["fileType"], "Plan")
        m = plan["agroScopeMeta"]
        self.assertEqual(m["taskId"], "TASK-2026-053")
        self.assertEqual(m["taskNumber"], 53)
        self.assertEqual(len(m["zones"]), 1)
        self.assertEqual(m["zones"][0]["zoneId"], 1)
        self.assertTrue(m["zones"][0]["waypointIndices"])
        # Zones start at item 2 (items 0=home, 1=takeoff are service items).
        self.assertEqual(m["zones"][0]["waypointIndices"][0], 2)
        self.assertLess(m["zones"][0]["waypointIndices"][-1], len(plan["mission"]["items"]))

    def test_returns_none_for_non_agroscope_field(self):
        self.field.agroscope_meta_serialized = ""
        self.field.save()
        md = load_mission(self.mission.id)
        plan = build_optimal_agroscope_plan(md, self.iterations, _transformer(), simple_holes_traversal=True)
        self.assertIsNone(plan)
