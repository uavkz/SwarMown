"""Turn an AgroScope task KML into a response MAVLink Plan JSON (US-2 + US-3).

End-to-end: parse the KML zones, plan a coverage route per zone with the
existing routing engine, then emit a single QGroundControl plan carrying the
``agroScopeMeta`` block so AgroScope can re-attach it to the task.

Usage:
    python scripts/agroscope_kml_to_plan.py path/to/task_53.kml \
        --drone-id 214 --grid-step 30 --altitude 100 \
        --out task_53_route.json --generated-at 2026-06-03T10:00:00Z

The route looks like real optimizer output: a coverage (zamboni) grid split
into multiple takeoff-landing cycles by the drone's battery range. There is no
truck road in an AgroScope survey, so a launch line is synthesized along the
southern edge of each zone's bounding box.
"""

import argparse
import json
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
django.setup()

from mainapp.models import Drone  # noqa: E402
from mainapp.service_routing import get_route  # noqa: E402
from mainapp.services_agroscope import build_agroscope_plan, parse_agroscope_kml  # noqa: E402


def _synth_road(points):
    """Launch line along the southern edge of the zone bbox, as [[lon, lat], ...]."""
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return [[min(lons), min(lats)], [max(lons), min(lats)]]


def plan_zone(zone, drone, grid_step, altitude, direction="simple", start="ne"):
    """Plan a coverage route for one zone. Returns an ordered list of waypoints."""
    field = [p[:] for p in zone["points"]]  # [lon, lat]
    road = _synth_road(zone["points"])
    _grid, flights, _car_wps, _init = get_route(
        car_move="no",
        direction=direction,
        start=start,
        field=field,
        grid_step=grid_step,
        road=road,
        drones=[drone],
        holes=[],
    )
    waypoints = []
    for flight in flights:
        for wp in flight:
            waypoints.append({"lat": wp["lat"], "lon": wp["lon"], "height": altitude})
    return waypoints, len(flights)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kml", help="Path to the AgroScope task KML")
    parser.add_argument("--drone-id", type=int, default=214, help="Drone DB id (default 214 / Ryze Tello)")
    parser.add_argument("--grid-step", type=float, default=30.0, help="Coverage grid step, meters")
    parser.add_argument("--altitude", type=float, default=100.0, help="Flight altitude AGL, meters")
    parser.add_argument("--direction", default="simple", help="Flight line direction ('simple' or degrees)")
    parser.add_argument("--start", default="ne", help="Start corner: ne/nw/se/sw")
    parser.add_argument("--generated-at", default=None, help="routeGeneratedAt ISO timestamp (UTC)")
    parser.add_argument("--out", default=None, help="Output JSON path")
    args = parser.parse_args()

    parsed = parse_agroscope_kml(args.kml)
    meta, zones = parsed["meta"], parsed["zones"]
    if not zones:
        sys.exit("No zones with valid polygons found in KML")

    drone = Drone.objects.get(id=args.drone_id)
    generated_at = args.generated_at or _utcnow_iso()

    plan_zones = []
    total_cycles = 0
    for zone in zones:
        waypoints, n_flights = plan_zone(zone, drone, args.grid_step, args.altitude, args.direction, args.start)
        total_cycles += n_flights
        plan_zones.append(
            {
                "zone_id": zone["zone_id"],
                "zone_name": zone["name"],
                "waypoints": waypoints,
            }
        )
        print(
            f"  {zone['name']}: {len(waypoints)} waypoints, {n_flights} takeoff-landing cycle(s)",
            file=sys.stderr,
        )

    plan = build_agroscope_plan(plan_zones, meta, generated_at)

    out_path = args.out or _default_out(args.kml, meta)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    print(
        f"Wrote {out_path}: {len(plan['mission']['items'])} items, "
        f"{len(zones)} zone(s), {total_cycles} takeoff-landing cycles, "
        f"drone={drone.name}",
        file=sys.stderr,
    )


def _utcnow_iso():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_out(kml_path, meta):
    num = meta.get("task_number") or "x"
    base = os.path.splitext(os.path.basename(kml_path))[0]
    return f"{base}_route_task{num}.json"


if __name__ == "__main__":
    main()
