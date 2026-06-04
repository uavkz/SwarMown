"""AgroScope integration: parse task KML (US-2) and build response plan JSON (US-3).

AgroScope exports a field's flight zones as a KML with task/zone metadata
(see Приложение 1). The optimizer imports it, plans a route per zone, and
returns a single MAVLink Plan JSON enriched with an ``agroScopeMeta`` block
(see Приложение 2) so AgroScope can re-attach the route to the task and split
it back into zones.
"""

import xml.etree.ElementTree as ET

_KML_NS = "http://www.opengis.net/kml/2.2"
_NS = {"kml": _KML_NS}

# Document-level ExtendedData fields we carry through (Приложение 1).
_DOC_META_FIELDS = (
    "source",
    "task_id",
    "task_number",
    "field_id",
    "field_name",
    "crop",
    "planned_date",
    "created_at",
)


def _extended_data(element):
    """Return {name: value} for an ExtendedData/Data block, namespace-agnostic."""
    data = {}
    for ed in list(element):
        if not ed.tag.endswith("ExtendedData"):
            continue
        for d in list(ed):
            if not d.tag.endswith("Data"):
                continue
            name = d.get("name")
            value_el = next((c for c in list(d) if c.tag.endswith("value")), None)
            if name and value_el is not None:
                data[name] = (value_el.text or "").strip()
    return data


def _findall_any_ns(root, local_name):
    """Find all elements with the given local tag name, ignoring namespace."""
    return [el for el in root.iter() if el.tag.endswith(local_name)]


def _parse_coordinates(text):
    """Parse a KML <coordinates> string into a list of [lon, lat] pairs.

    KML coordinates are "lon,lat[,alt]" tuples. We keep [lon, lat] order, which
    is what the routing engine expects for the ``field`` argument.
    """
    points = []
    for token in (text or "").strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
            except ValueError:
                continue
            points.append([lon, lat])
    # KML rings repeat the first point at the end — drop the duplicate.
    if len(points) >= 4 and points[0] == points[-1]:
        points = points[:-1]
    return points


def parse_agroscope_kml(source):
    """Parse an AgroScope task KML into {"meta": {...}, "zones": [...]}.

    ``source`` is a path, file object, or anything ``ElementTree.parse`` accepts.

    Backward compatible with the old "Exported Polygons" KML that lacks the
    task/zone metadata: missing meta fields are ``None`` and ``zone_id`` falls
    back to the placemark name or its 1-based position.

    Each zone: {"zone_id", "name", "description", "task_id", "points": [[lon, lat], ...]}.
    Zones without a valid polygon (< 3 points) are skipped.
    """
    root = ET.parse(source).getroot()
    document = next((el for el in root.iter() if el.tag.endswith("Document")), root)

    doc_data = _extended_data(document)
    doc_name = next((c.text for c in list(document) if c.tag.endswith("name") and c.text), None)
    meta = {"name": (doc_name or "").strip() or None}
    for field in _DOC_META_FIELDS:
        meta[field] = doc_data.get(field) or None

    zones = []
    for pm in _findall_any_ns(root, "Placemark"):
        polygon = next((el for el in pm.iter() if el.tag.endswith("Polygon")), None)
        if polygon is None:
            continue
        # Prefer the outer boundary; fall back to the first coordinates block.
        outer = next((el for el in polygon.iter() if el.tag.endswith("outerBoundaryIs")), polygon)
        coords_el = next((el for el in outer.iter() if el.tag.endswith("coordinates")), None)
        if coords_el is None:
            continue
        points = _parse_coordinates(coords_el.text)
        if len(points) < 3:
            continue

        pm_data = _extended_data(pm)
        name = next((c.text for c in list(pm) if c.tag.endswith("name") and c.text), None)
        name = (name or "").strip()
        description = next((c.text for c in list(pm) if c.tag.endswith("description") and c.text), None)
        zone_id = pm_data.get("zone_id") or name or str(len(zones) + 1)

        zones.append(
            {
                "zone_id": zone_id,
                "name": name or f"Зона {len(zones) + 1}",
                "description": (description or "").strip() or None,
                "task_id": pm_data.get("task_id") or meta.get("task_id"),
                "points": points,
            }
        )
    return {"meta": meta, "zones": zones}


def _to_int(value):
    """Best-effort int conversion; returns the original value if not numeric."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _mission_item(index, lat, lon, altitude):
    """Build a single MAVLink SimpleItem, matching utils_mavlink.create_plan_file.

    index 0 -> home placeholder (command 530), 1 -> takeoff (22), rest -> waypoint (16).
    """
    if index == 0:
        return {
            "AMSLAltAboveTerrain": None,
            "Altitude": altitude,
            "AltitudeMode": None,
            "autoContinue": True,
            "command": 530,
            "doJumpId": 1,
            "frame": 2,
            "params": [0, 2, None, None, None, None, None],
            "type": "SimpleItem",
        }
    command = 22 if index == 1 else 16
    return {
        "AMSLAltAboveTerrain": None,
        "Altitude": altitude,
        "AltitudeMode": 0,
        "autoContinue": True,
        "command": command,
        "doJumpId": index + 1,
        "frame": 3,
        "params": [0, 0, 0, None, lat, lon, altitude],
        "type": "SimpleItem",
    }


def build_agroscope_plan(zones, meta, route_generated_at, altitude_world=855):
    """Build a single QGroundControl MAVLink Plan with an ``agroScopeMeta`` block.

    ``zones``: list of {"zone_id", "zone_name", "waypoints": [{"lat","lon","height"}, ...]}.
    Waypoints must already be ordered (zamboni traversal incl. fly-to/fly-back transits).
    ``meta``: the dict from parse_agroscope_kml()["meta"].
    ``route_generated_at``: ISO-8601 timestamp string (e.g. "2026-06-03T10:00:00Z").

    Items match the standard QGroundControl layout (== utils_mavlink.create_plan_file):
    items[0] = home/settings (command 530), items[1] = takeoff (command 22), the
    rest = waypoints (command 16). Each zone's ``waypointIndices`` are contiguous
    mission.items indices starting at 2 — items 0 (home) and 1 (takeoff) are
    service items and belong to no zone, exactly like the integration example.
    """
    # Flatten all zone waypoints in order, remembering how many belong to each zone.
    flat = []
    zone_counts = []
    for zone in zones:
        wps = zone["waypoints"]
        if not wps:
            continue
        zone_counts.append((zone, len(wps)))
        flat.extend(wps)

    first_point = flat[0] if flat else None
    altitude = first_point["height"] if first_point else 80
    # item i corresponds to flat[i]; item 0 hides coords (home), item 1 is takeoff.
    plan_items = [_mission_item(i, wp["lat"], wp["lon"], wp.get("height", altitude)) for i, wp in enumerate(flat)]

    agro_zones = []
    cursor = 0
    for zone, count in zone_counts:
        # Skip service items 0 (home) and 1 (takeoff); they belong to no zone.
        zone_indices = [i for i in range(cursor, cursor + count) if i >= 2]
        cursor += count
        agro_zones.append(
            {
                "zoneId": _to_int(zone["zone_id"]),
                "zoneName": zone.get("zone_name") or zone.get("name"),
                "waypointIndices": zone_indices,
            }
        )

    home_lat = first_point["lat"] if first_point else 0
    home_lon = first_point["lon"] if first_point else 0

    return {
        "fileType": "Plan",
        "geoFence": {"circles": [], "polygons": [], "version": 2},
        "groundStation": "QGroundControl",
        "mission": {
            "cruiseSpeed": 15,
            "firmwareType": 12,
            "globalPlanAltitudeMode": 1,
            "hoverSpeed": 5,
            "items": plan_items,
            "plannedHomePosition": [home_lat, home_lon, altitude_world],
            "vehicleType": 2,
            "version": 2,
        },
        "rallyPoints": {"points": [], "version": 2},
        "version": 1,
        "agroScopeMeta": {
            "taskId": meta.get("task_id"),
            "taskNumber": _to_int(meta.get("task_number")),
            "fieldId": meta.get("field_id"),
            "fieldName": meta.get("field_name"),
            "crop": meta.get("crop"),
            "plannedDate": meta.get("planned_date"),
            "routeGeneratedAt": route_generated_at,
            "zones": agro_zones,
        },
    }
