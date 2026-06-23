"""Add the C5varied campaign: 5 elongated fields at different orientations.

Motivation: the other campaigns use near-square, axis-aligned rectangles, so the
optimal coverage *direction* is the same for every field and per-field direction
optimization has nothing to do (the single_direction ablation looks free). To
test direction honestly we need fields whose optimal flight-line direction
differs between fields -- i.e. elongated rectangles at different orientations:
flying ALONG a thin field's long axis needs few long passes (few turns), flying
ACROSS needs many short passes (many turns), and the best direction therefore
varies field-to-field.

Additive + idempotent: only touches the EXP:C5varied campaign and its fields,
leaving the rest of the experiment data (and the running matrix) untouched.
Updates scripts/exp_manifest.json in place.

Run: venv39\\Scripts\\python.exe scripts/exp_campaign_varied.py
"""

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
import django

django.setup()

from django.contrib.auth.models import User  # noqa: E402

from mainapp.models import Campaign, CampaignField, Drone, Field  # noqa: E402
from scripts.exp_campaigns import (  # noqa: E402
    DRONE_IDS,
    EXP_USER,
    GRID_STEP,
    HOURLY_PRICE,
    KM_PER_DEG_LAT,
    KM_PER_DEG_LON,
    LAT0,
    LON0,
    MANIFEST_PATH,
    ROAD_GAP,
    START_PRICE,
    TRUCK_SPEED,
)


def elong_rect(clat, clon, length_km, width_km, angle_deg):
    """Elongated rectangle, long axis rotated `angle_deg` from east. [lat,lon]."""
    hl, hw = length_km / 2.0, width_km / 2.0
    a = math.radians(angle_deg)
    corners = []
    for x, y in [(-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw)]:  # local km (east, north)
        xr = x * math.cos(a) - y * math.sin(a)
        yr = x * math.sin(a) + y * math.cos(a)
        corners.append([clat + yr / KM_PER_DEG_LAT, clon + xr / KM_PER_DEG_LON])
    return corners


def road_for(corners):
    """West->east road just south of the field's bounding box. [lat,lon]."""
    lats = [c[0] for c in corners]
    lons = [c[1] for c in corners]
    y = min(lats) - ROAD_GAP
    return [[y, min(lons)], [y, max(lons)]]


def main():
    user, _ = User.objects.get_or_create(username=EXP_USER)
    Campaign.objects.filter(owner=user, name="EXP:C5varied").delete()
    Field.objects.filter(owner=user, name__startswith="EXP:c5v-").delete()

    drones = list(Drone.objects.filter(id__in=DRONE_IDS))

    # 5 elongated fields, distinct orientations, moderate spread (~3-8 km).
    specs = [
        ("c5v-A", LAT0, LON0, 1.6, 0.4, 0),
        ("c5v-B", LAT0 + 0.010, LON0 + 0.045, 1.6, 0.4, 40),
        ("c5v-C", LAT0 + 0.002, LON0 + 0.090, 1.8, 0.35, 80),
        ("c5v-D", LAT0 + 0.040, LON0 + 0.020, 1.4, 0.45, 120),
        ("c5v-E", LAT0 + 0.030, LON0 + 0.075, 1.6, 0.4, 160),
    ]

    campaign = Campaign.objects.create(
        owner=user,
        name="EXP:C5varied",
        grid_step=GRID_STEP,
        start_price=START_PRICE,
        hourly_price=HOURLY_PRICE,
        truck_speed_kmh=TRUCK_SPEED,
    )
    campaign.drones.add(*drones)
    for order, (name, clat, clon, length, width, angle) in enumerate(specs):
        corners = elong_rect(clat, clon, length, width, angle)
        field = Field.objects.create(
            owner=user,
            name=f"EXP:{name}",
            points_serialized=json.dumps(corners),
            road_serialized=json.dumps(road_for(corners)),
            holes_serialized="[]",
        )
        CampaignField.objects.create(campaign=campaign, field=field, default_order=order)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["C5varied"] = campaign.id
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[{campaign.id}] EXP:C5varied — 5 elongated fields, orientations {[s[5] for s in specs]}")
    print(f"manifest updated: C5varied -> {campaign.id}")


if __name__ == "__main__":
    main()
