"""Deterministic generator for multi-field experiment campaigns.

Creates a fixed, reproducible set of campaigns with controlled geometry so the
experiment matrix (operator comparison, ablation, scaling, transit sensitivity)
runs against known inputs. Idempotent: deletes any previously generated
experiment data (owned by the EXP_USER) and recreates it from scratch.

Coordinate convention (matches the rest of the codebase): Field.points_serialized
and holes_serialized store [lat, lon] pairs; load_campaign() swaps to [lon, lat]
internally. Roads run west -> east consistently so inter-field transit
(road_a[-1] -> road_b[0]) is computed exit-east -> entry-west of the next field.

Run:
    venv39\\Scripts\\python.exe scripts/exp_campaigns.py
Writes scripts/exp_manifest.json mapping role -> campaign_id.
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

EXP_USER = "exp_runner"
MANIFEST_PATH = Path(__file__).resolve().parent / "exp_manifest.json"

# Drones attached to every campaign (varied range & price so the single_drones
# ablation has something to optimise). IDs are stable in this DB.
DRONE_IDS = [203, 209, 215]  # Phantom 4 (range 13.6), Mavic 2 (37.2), Autel Evo II (48)

# Campaign cost/grid defaults (shared so cross-campaign comparison is clean).
GRID_STEP = 200.0
START_PRICE = 3.0
HOURLY_PRICE = 10.0
TRUCK_SPEED = 40.0

# Base location: agricultural region near Astana, KZ.
LAT0, LON0 = 51.10, 71.40
# At lat 51: 1 deg lat ~= 111.2 km, 1 deg lon ~= 70.1 km.
KM_PER_DEG_LAT = 111.2
KM_PER_DEG_LON = 111.2 * math.cos(math.radians(LAT0))  # ~70.1

# Default field half-extent (~1.0 km N-S x ~1.0 km E-W).
HLAT = 0.0045
HLON = 0.0071
ROAD_GAP = 0.0015  # road sits ~165 m south of the field's south edge


def rect(clat, clon, hlat=HLAT, hlon=HLON):
    """Axis-aligned rectangle field as [lat, lon] corners (CCW from SW)."""
    return [
        [clat - hlat, clon - hlon],
        [clat - hlat, clon + hlon],
        [clat + hlat, clon + hlon],
        [clat + hlat, clon - hlon],
    ]


def road_south(clat, clon, hlat=HLAT, hlon=HLON):
    """West->east road just south of the field, as [lat, lon] points."""
    y = clat - hlat - ROAD_GAP
    return [[y, clon - hlon], [y, clon + hlon]]


def hole(clat, clon, hh_lat, hh_lon):
    """Small rectangular hole centered in the field, [lat, lon] corners."""
    return [
        [clat - hh_lat, clon - hh_lon],
        [clat - hh_lat, clon + hh_lon],
        [clat + hh_lat, clon + hh_lon],
        [clat + hh_lat, clon - hh_lon],
    ]


def km(dlat, dlon):
    return math.hypot(dlat * KM_PER_DEG_LAT, dlon * KM_PER_DEG_LON)


# --- Campaign layouts -------------------------------------------------------
# Each field spec: (name, center_lat, center_lon, half_lat, half_lon, holes)
# holes is a list of hole polygons ([lat,lon] corner lists), possibly empty.


def _f(name, clat, clon, hlat=HLAT, hlon=HLON, holes=None):
    return {"name": name, "clat": clat, "clon": clon, "hlat": hlat, "hlon": hlon, "holes": holes or []}


def build_layouts():
    layouts = {}

    # C2-close: two adjacent fields (~1.4 km apart). Transit negligible.
    layouts["C2close"] = [
        _f("c2c-A", LAT0, LON0),
        _f("c2c-B", LAT0, LON0 + 0.020),
    ]

    # C2-far: two fields ~46 km apart. Transit dominates.
    layouts["C2far"] = [
        _f("c2f-A", LAT0, LON0),
        _f("c2f-B", LAT0, LON0 + 0.650),
    ]

    # C3-line: collinear, small gap then large gap. A-B-C >> A-C-B.
    layouts["C3line"] = [
        _f("c3l-A", LAT0, LON0),
        _f("c3l-B", LAT0, LON0 + 0.040),
        _f("c3l-C", LAT0, LON0 + 0.600),
    ]

    # C3-tri: 3 fields on a circle (equal pairwise ground distance) -> order
    # should barely matter. lon scaled by 1/cos(lat) for true equidistance.
    R = 0.13
    cen_lat, cen_lon = LAT0 + 0.10, LON0 + 0.20
    tri = []
    for i, ang in enumerate((90, 210, 330)):
        dlat = R * math.sin(math.radians(ang))
        dlon = R / math.cos(math.radians(LAT0)) * math.cos(math.radians(ang))
        tri.append(_f(f"c3t-{chr(65 + i)}", cen_lat + dlat, cen_lon + dlon))
    layouts["C3tri"] = tri

    # C5-mixed: two close clusters + one far field. Tests grouping.
    layouts["C5mixed"] = [
        _f("c5m-A", LAT0, LON0),
        _f("c5m-B", LAT0 + 0.006, LON0 + 0.022),  # cluster 1 with A
        _f("c5m-C", LAT0, LON0 + 0.220),  # cluster 2 (~15 km east)
        _f("c5m-D", LAT0 + 0.006, LON0 + 0.242),  # cluster 2 with C
        _f("c5m-E", LAT0 + 0.350, LON0 + 0.020),  # far north (~39 km)
    ]

    # C5-holes: 5 fields of varied size, 3 with holes (1 / 2 / many), moderate
    # spread (~5-15 km). The "some with holes, some without" requirement.
    big_h, big_w = 0.0065, 0.0100  # ~1.45 km x 1.4 km
    layouts["C5holes"] = [
        _f("c5h-A", LAT0, LON0, big_h, big_w, holes=[hole(LAT0, LON0, 0.0018, 0.0026)]),
        _f("c5h-B", LAT0 + 0.004, LON0 + 0.030),  # no holes
        _f(
            "c5h-C",
            LAT0,
            LON0 + 0.075,
            big_h,
            big_w,
            holes=[
                hole(LAT0, LON0 + 0.075 - 0.004, 0.0030, 0.0012),
                hole(LAT0, LON0 + 0.075 + 0.004, 0.0030, 0.0012),
            ],
        ),
        _f("c5h-D", LAT0 + 0.090, LON0 + 0.030),  # no holes (~10 km north)
        _f(
            "c5h-E",
            LAT0 + 0.050,
            LON0 + 0.110,
            big_h,
            big_w,
            holes=[
                hole(LAT0 + 0.050 - 0.0025, LON0 + 0.110 - 0.0035, 0.0010, 0.0014),
                hole(LAT0 + 0.050 + 0.0025, LON0 + 0.110 + 0.0035, 0.0010, 0.0014),
                hole(LAT0 + 0.050 + 0.0025, LON0 + 0.110 - 0.0035, 0.0010, 0.0014),
            ],
        ),
    ]

    # C10-grid: 2x5 grid, ~3 km spacing. Scaling test.
    grid = []
    for r in range(2):
        for c in range(5):
            idx = r * 5 + c
            grid.append(_f(f"c10-{idx:02d}", LAT0 + r * 0.025, LON0 + c * 0.040))
    layouts["C10grid"] = grid

    return layouts


def make_field(owner, spec):
    holes_serialized = json.dumps(spec["holes"]) if spec["holes"] else "[]"
    return Field.objects.create(
        owner=owner,
        name=f"EXP:{spec['name']}",
        points_serialized=json.dumps(rect(spec["clat"], spec["clon"], spec["hlat"], spec["hlon"])),
        road_serialized=json.dumps(road_south(spec["clat"], spec["clon"], spec["hlat"], spec["hlon"])),
        holes_serialized=holes_serialized,
    )


def main():
    user, _ = User.objects.get_or_create(username=EXP_USER)

    # Idempotent reset: drop previously generated experiment campaigns + fields.
    Campaign.objects.filter(owner=user).delete()
    Field.objects.filter(owner=user, name__startswith="EXP:").delete()

    drones = list(Drone.objects.filter(id__in=DRONE_IDS))
    if len(drones) != len(DRONE_IDS):
        print(f"WARNING: expected drones {DRONE_IDS}, found {[d.id for d in drones]}")

    layouts = build_layouts()
    manifest = {}

    for role, specs in layouts.items():
        campaign = Campaign.objects.create(
            owner=user,
            name=f"EXP:{role}",
            grid_step=GRID_STEP,
            start_price=START_PRICE,
            hourly_price=HOURLY_PRICE,
            truck_speed_kmh=TRUCK_SPEED,
        )
        campaign.drones.add(*drones)
        centers = []
        for order, spec in enumerate(specs):
            field = make_field(user, spec)
            CampaignField.objects.create(campaign=campaign, field=field, default_order=order)
            centers.append((spec["clat"], spec["clon"]))
        manifest[role] = campaign.id

        # Verification: pairwise transit distances along default order.
        seg = []
        for i in range(1, len(centers)):
            dlat = centers[i][0] - centers[i - 1][0]
            dlon = centers[i][1] - centers[i - 1][1]
            seg.append(round(km(dlat, dlon), 1))
        n_holes = sum(len(s["holes"]) for s in specs)
        print(f"[{campaign.id}] EXP:{role:9s} fields={len(specs)} holes={n_holes} consec-gaps(km)={seg}")

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest -> {MANIFEST_PATH}")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
