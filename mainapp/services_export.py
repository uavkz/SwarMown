"""Export services: CSV, MavLink JSON, elevation resolution."""

import asyncio
import csv
import json
import zipfile
from io import BytesIO

from django.http import HttpResponse

from mainapp.utils_gis import get_elevations_for_points_dict
from mainapp.utils_mavlink import create_plan_file


def _resolve_elevations(waypoints_list):
    """Fetch terrain elevations for all waypoints. Returns {(lat, lon): elevation}."""
    all_points = []
    for waypoints in waypoints_list:
        for wp in waypoints:
            all_points.append([wp["lat"], wp["lon"]])
    return asyncio.run(get_elevations_for_points_dict(all_points))


def _get_height(waypoint, elevations_dict, height_offset, height_absolute_override=None):
    """Compute absolute height for a waypoint."""
    if height_absolute_override is not None:
        return float(height_absolute_override), float(height_absolute_override)
    elevation = elevations_dict[(round(waypoint["lat"], 3), round(waypoint["lon"], 3))]
    return elevation + height_offset, elevation


def export_csv(waypoints_list, height_offset=450.0, height_absolute_override=None):
    """Generate a CSV HttpResponse with waypoint data."""
    elevations = _resolve_elevations(waypoints_list)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="waypoints.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "lat",
            "lon",
            "height",
            "height_global",
            "drone_id",
            "drone_name",
            "drone_model",
            "speed",
            "acceleration",
            "spray_on",
        ]
    )
    for waypoints in waypoints_list:
        for wp in waypoints:
            height, height_global = _get_height(wp, elevations, height_offset, height_absolute_override)
            writer.writerow(
                [
                    wp["lat"],
                    wp["lon"],
                    height,
                    height_global,
                    wp["drone"]["id"],
                    wp["drone"]["name"],
                    wp["drone"]["model"],
                    wp["speed"],
                    wp["acceleration"],
                    wp["spray_on"],
                ]
            )
    return response


def export_mavlink_json(waypoints_list, height_offset=450.0, height_absolute_override=None):
    """Generate MavLink plan JSON file(s) as HttpResponse (single JSON or zip)."""
    elevations = _resolve_elevations(waypoints_list)
    data = []
    for waypoints in waypoints_list:
        for wp in waypoints:
            height, height_global = _get_height(wp, elevations, height_offset, height_absolute_override)
            data.append(
                {
                    "lat": wp["lat"],
                    "lon": wp["lon"],
                    "height": height,
                    "height_global": height_global,
                    "drone_id": wp["drone"]["id"],
                    "drone_name": wp["drone"]["name"],
                    "drone_model": wp["drone"]["model"],
                    "speed": wp["speed"],
                    "acceleration": wp["acceleration"],
                    "spray_on": wp["spray_on"],
                }
            )

    drone_ids = list({d["drone_id"] for d in data})
    plans = [
        create_plan_file(
            [[d["lat"], d["lon"], d["height"]] for d in data if d["drone_id"] == did],
            did,
        )
        for did in drone_ids
    ]

    if len(plans) == 1:
        response = HttpResponse(json.dumps(plans[0]), content_type="application/json")
        response["Content-Disposition"] = 'attachment; filename="plan.json"'
    else:
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for i, (plan, did) in enumerate(zip(plans, drone_ids)):
                zf.writestr(f"plan_{did}_{i}.json", json.dumps(plan))
        buf.seek(0)
        response = HttpResponse(buf, content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="plans.zip"'

    return response
