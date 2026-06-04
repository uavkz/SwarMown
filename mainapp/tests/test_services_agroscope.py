import io

from django.test import TestCase

from mainapp.services_agroscope import build_agroscope_plan, parse_agroscope_kml

# AgroScope task KML (Приложение 1) — two zones with full metadata.
NEW_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Задание №53 - Лесополоса 150 га</name>
    <ExtendedData>
      <Data name="source"><value>AgroScope</value></Data>
      <Data name="task_id"><value>TASK-2026-053</value></Data>
      <Data name="task_number"><value>53</value></Data>
      <Data name="field_id"><value>120</value></Data>
      <Data name="field_name"><value>Лесополоса 150 га</value></Data>
      <Data name="crop"><value>Подсолнечник</value></Data>
      <Data name="planned_date"><value>2026-05-31</value></Data>
      <Data name="created_at"><value>2026-05-29T12:54:38Z</value></Data>
    </ExtendedData>
    <Placemark>
      <name>Зона 1</name>
      <description>Задание №53 | зона 1</description>
      <ExtendedData>
        <Data name="zone_id"><value>1</value></Data>
        <Data name="task_id"><value>TASK-2026-053</value></Data>
      </ExtendedData>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>
        82.0,50.0,0 82.1,50.0,0 82.1,50.1,0 82.0,50.1,0 82.0,50.0,0
      </coordinates></LinearRing></outerBoundaryIs></Polygon>
    </Placemark>
    <Placemark>
      <name>Зона 2</name>
      <ExtendedData>
        <Data name="zone_id"><value>2</value></Data>
      </ExtendedData>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>
        83.0,51.0,0 83.1,51.0,0 83.1,51.1,0 83.0,51.0,0
      </coordinates></LinearRing></outerBoundaryIs></Polygon>
    </Placemark>
  </Document>
</kml>"""

# Old-style plain polygon KML — no AgroScope metadata.
OLD_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Exported Polygons</name>
    <Placemark>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>
        70.0,40.0,0 70.1,40.0,0 70.1,40.1,0 70.0,40.0,0
      </coordinates></LinearRing></outerBoundaryIs></Polygon>
    </Placemark>
  </Document>
</kml>"""


class ParseAgroscopeKmlTests(TestCase):
    def test_parses_document_meta(self):
        meta = parse_agroscope_kml(io.StringIO(NEW_KML))["meta"]
        self.assertEqual(meta["task_id"], "TASK-2026-053")
        self.assertEqual(meta["task_number"], "53")
        self.assertEqual(meta["field_id"], "120")
        self.assertEqual(meta["field_name"], "Лесополоса 150 га")
        self.assertEqual(meta["crop"], "Подсолнечник")
        self.assertEqual(meta["planned_date"], "2026-05-31")
        self.assertEqual(meta["source"], "AgroScope")

    def test_parses_zones(self):
        zones = parse_agroscope_kml(io.StringIO(NEW_KML))["zones"]
        self.assertEqual(len(zones), 2)
        self.assertEqual(zones[0]["zone_id"], "1")
        self.assertEqual(zones[0]["name"], "Зона 1")
        self.assertEqual(zones[0]["task_id"], "TASK-2026-053")
        self.assertIn("зона 1", zones[0]["description"])

    def test_coordinates_are_lon_lat_and_ring_closed_point_dropped(self):
        zones = parse_agroscope_kml(io.StringIO(NEW_KML))["zones"]
        pts = zones[0]["points"]
        self.assertEqual(pts, [[82.0, 50.0], [82.1, 50.0], [82.1, 50.1], [82.0, 50.1]])

    def test_zone2_task_id_falls_back_to_document(self):
        zones = parse_agroscope_kml(io.StringIO(NEW_KML))["zones"]
        # Зона 2 has no per-placemark task_id -> inherits document task_id.
        self.assertEqual(zones[1]["task_id"], "TASK-2026-053")

    def test_old_kml_backward_compatible(self):
        parsed = parse_agroscope_kml(io.StringIO(OLD_KML))
        self.assertIsNone(parsed["meta"]["task_id"])
        self.assertEqual(len(parsed["zones"]), 1)
        # zone_id falls back to 1-based position when absent.
        self.assertEqual(parsed["zones"][0]["zone_id"], "1")


def _zone(zone_id, name, n):
    return {
        "zone_id": zone_id,
        "zone_name": name,
        "waypoints": [{"lat": 50.0 + i * 0.001, "lon": 82.0 + i * 0.001, "height": 100} for i in range(n)],
    }


class BuildAgroscopePlanTests(TestCase):
    def setUp(self):
        self.meta = parse_agroscope_kml(io.StringIO(NEW_KML))["meta"]
        self.zones = [_zone("1", "Зона 1", 5), _zone("2", "Зона 2", 3)]
        self.plan = build_agroscope_plan(self.zones, self.meta, "2026-06-03T10:00:00Z")

    def test_is_mavlink_plan(self):
        self.assertEqual(self.plan["fileType"], "Plan")
        self.assertEqual(self.plan["groundStation"], "QGroundControl")
        self.assertIn("items", self.plan["mission"])

    def test_item_count_is_waypoints_plus_home(self):
        # 5 + 3 waypoints + 1 home placeholder.
        self.assertEqual(len(self.plan["mission"]["items"]), 9)

    def test_home_and_takeoff_commands(self):
        items = self.plan["mission"]["items"]
        self.assertEqual(items[0]["command"], 530)
        self.assertEqual(items[1]["command"], 22)
        self.assertEqual(items[2]["command"], 16)

    def test_agroscope_meta_fields(self):
        m = self.plan["agroScopeMeta"]
        self.assertEqual(m["taskId"], "TASK-2026-053")
        self.assertEqual(m["taskNumber"], 53)  # coerced to int
        self.assertEqual(m["fieldId"], "120")
        self.assertEqual(m["plannedDate"], "2026-05-31")
        self.assertEqual(m["routeGeneratedAt"], "2026-06-03T10:00:00Z")

    def test_waypoint_indices_contiguous_complete_and_disjoint(self):
        zones = self.plan["agroScopeMeta"]["zones"]
        self.assertEqual(zones[0]["zoneId"], 1)
        self.assertEqual(zones[0]["waypointIndices"], [1, 2, 3, 4, 5])
        self.assertEqual(zones[1]["waypointIndices"], [6, 7, 8])
        all_idx = [i for z in zones for i in z["waypointIndices"]]
        n_items = len(self.plan["mission"]["items"])
        # Every non-home item belongs to exactly one zone.
        self.assertEqual(sorted(all_idx), list(range(1, n_items)))

    def test_indices_reference_correct_coordinates(self):
        items = self.plan["mission"]["items"]
        first_idx = self.plan["agroScopeMeta"]["zones"][0]["waypointIndices"][0]
        wp = self.zones[0]["waypoints"][0]
        self.assertAlmostEqual(items[first_idx]["params"][4], wp["lat"])
        self.assertAlmostEqual(items[first_idx]["params"][5], wp["lon"])
