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

# Experiment fleet (v2): five drone classes with genuine Pareto structure and
# NO dominated model under the one-crew cost model (salary is per hour, not per
# model). Axes, from light to heavy class: agility falls (turn slowdown and its
# floor worsen), cruise speed and battery range rise, per-launch cost (c_cycle,
# battery/tank cycle) rises, per-flight-hour cost FALLS (amortized maintenance
# per hour declines with platform class). Net effect: small/turn-dense parcels
# favour light models (cheap launches, agile, hourly premium irrelevant on
# short flights); large parcels favour heavy models (few launches, cheap
# hours, clumsiness amortized over long straight lines). Stock DB drones are
# left untouched; these are created by name (get_or_create).
FLEET_SPECS = [
    dict(
        name="EXP Scout (Mini-class)",
        model="scout",
        max_speed=58.0,
        max_distance_no_load=12.0,
        slowdown_ratio_per_degree=0.002,
        min_slowdown_ratio=0.40,
        price_per_cycle=0.3,
        price_per_kilometer=0.010,
        price_per_hour=4.8,
        weight=0.25,
        max_load=0.25,
    ),
    dict(
        name="EXP Light (Phantom-class)",
        model="light",
        max_speed=72.0,
        max_distance_no_load=14.0,
        slowdown_ratio_per_degree=0.004,
        min_slowdown_ratio=0.15,
        price_per_cycle=0.8,
        price_per_kilometer=0.020,
        price_per_hour=3.0,
        weight=1.4,
        max_load=0.5,
    ),
    dict(
        name="EXP Mid (Mavic-class)",
        model="mid",
        max_speed=72.0,
        max_distance_no_load=37.0,
        slowdown_ratio_per_degree=0.005,
        min_slowdown_ratio=0.10,
        price_per_cycle=1.7,
        price_per_kilometer=0.045,
        price_per_hour=2.4,
        weight=0.9,
        max_load=0.5,
    ),
    dict(
        name="EXP Long (Evo-class)",
        model="long",
        max_speed=72.0,
        max_distance_no_load=48.0,
        slowdown_ratio_per_degree=0.0065,
        min_slowdown_ratio=0.05,
        price_per_cycle=3.0,
        price_per_kilometer=0.060,
        price_per_hour=1.6,
        weight=1.2,
        max_load=0.9,
    ),
    dict(
        name="EXP Heavy (M300-class)",
        model="heavy",
        max_speed=82.0,
        max_distance_no_load=60.0,
        slowdown_ratio_per_degree=0.008,
        min_slowdown_ratio=0.03,
        price_per_cycle=6.0,
        price_per_kilometer=0.080,
        price_per_hour=1.0,
        weight=6.3,
        max_load=2.7,
    ),
]


def get_fleet():
    """The five EXP fleet-v2 drones (created if missing), in class order."""
    drones = []
    for spec in FLEET_SPECS:
        d, created = Drone.objects.get_or_create(name=spec["name"], defaults=spec)
        if not created:
            # keep DB in sync with the specs above (idempotent redefinition)
            for k, v in spec.items():
                setattr(d, k, v)
            d.save()
        drones.append(d)
    return drones


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


# --- Realistic field shapes ---------------------------------------------------
# Normalized corner templates in local (east, north) coordinates, roughly unit
# extent. Real agricultural parcels are rarely rectangular: they follow roads,
# ditches and old cadastre lines. Templates are hand-crafted (deterministic).
SHAPES = {
    # irregular convex quadrilateral (no parallel sides)
    "quad": [(-0.55, -0.45), (0.52, -0.55), (0.6, 0.42), (-0.44, 0.5)],
    # trapezoid (one pair of near-parallel sides)
    "trap": [(-0.65, -0.5), (0.65, -0.5), (0.34, 0.5), (-0.3, 0.5)],
    # pentagon (clipped corner field)
    "pent": [(-0.5, -0.52), (0.5, -0.5), (0.62, 0.14), (0.02, 0.55), (-0.6, 0.2)],
    # triangle-ish (sharp wedge with a clipped tip)
    "tri": [(-0.66, -0.45), (0.65, -0.52), (0.16, 0.55), (-0.2, 0.55)],
    # L-shape (non-convex parcel)
    "ell": [(-0.6, -0.5), (0.6, -0.5), (0.6, 0.08), (0.04, 0.08), (0.04, 0.55), (-0.6, 0.55)],
}


def _shoelace(pts):
    n = len(pts)
    return 0.5 * abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n)))


def poly(clat, clon, shape, area_ha, rot_deg=0.0):
    """Realistic field polygon as [lat, lon] corners.

    Scales the named template to `area_ha` hectares, rotates it by `rot_deg`
    and places it at (clat, clon). Deterministic.
    """
    tpl = SHAPES[shape]
    scale = math.sqrt((area_ha / 100.0) / _shoelace(tpl))  # ha -> km^2
    a = math.radians(rot_deg)
    corners = []
    for x, y in tpl:
        xs, ys = x * scale, y * scale
        xr = xs * math.cos(a) - ys * math.sin(a)
        yr = xs * math.sin(a) + ys * math.cos(a)
        corners.append([clat + yr / KM_PER_DEG_LAT, clon + xr / KM_PER_DEG_LON])
    return corners


def road_south_of(corners):
    """West->east road just south of the polygon's bounding box. [lat, lon]."""
    lats = [c[0] for c in corners]
    lons = [c[1] for c in corners]
    y = min(lats) - ROAD_GAP
    return [[y, min(lons)], [y, max(lons)]]


def _fp(name, clat, clon, shape, area_ha, rot_deg=0.0, holes=None):
    """Field spec with an explicit realistic polygon."""
    return {"name": name, "corners": poly(clat, clon, shape, area_ha, rot_deg), "holes": holes or []}


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
    """Square/rectangular field spec (kept for control campaigns)."""
    return {"name": name, "corners": rect(clat, clon, hlat, hlon), "holes": holes or []}


def build_layouts():
    """Campaign layouts. C2close/C2far keep deliberately square fields as
    controlled baselines; every other campaign uses realistic irregular
    parcels (SHAPES templates at varied rotations), area-matched to the
    original square design so day-length/feasibility calibration carries over.
    """
    layouts = {}

    # C2-close: two adjacent square fields (~1.4 km apart). Transit negligible.
    layouts["C2close"] = [
        _f("c2c-A", LAT0, LON0),
        _f("c2c-B", LAT0, LON0 + 0.020),
    ]

    # C2-far: two square fields ~46 km apart. Transit dominates.
    layouts["C2far"] = [
        _f("c2f-A", LAT0, LON0),
        _f("c2f-B", LAT0, LON0 + 0.650),
    ]

    # C3-line: collinear, small gap then large gap. A-B-C >> A-C-B.
    layouts["C3line"] = [
        _fp("c3l-A", LAT0, LON0, "quad", 100, 8),
        _fp("c3l-B", LAT0, LON0 + 0.040, "trap", 100, -15),
        _fp("c3l-C", LAT0, LON0 + 0.600, "pent", 100, 30),
    ]

    # C3-tri: 3 IDENTICAL fields on a circle (equal pairwise ground distance)
    # -> order should barely matter. lon scaled by 1/cos(lat) for equidistance.
    R = 0.13
    cen_lat, cen_lon = LAT0 + 0.10, LON0 + 0.20
    tri = []
    for i, ang in enumerate((90, 210, 330)):
        dlat = R * math.sin(math.radians(ang))
        dlon = R / math.cos(math.radians(LAT0)) * math.cos(math.radians(ang))
        tri.append(_fp(f"c3t-{chr(65 + i)}", cen_lat + dlat, cen_lon + dlon, "pent", 100, i * 120))
    layouts["C3tri"] = tri

    # C5-mixed: two close clusters + one far field. Tests grouping.
    layouts["C5mixed"] = [
        _fp("c5m-A", LAT0, LON0, "quad", 100, 12),
        _fp("c5m-B", LAT0 + 0.006, LON0 + 0.022, "trap", 100, -20),  # cluster 1 with A
        _fp("c5m-C", LAT0, LON0 + 0.220, "pent", 100, 65),  # cluster 2 (~15 km east)
        _fp("c5m-D", LAT0 + 0.006, LON0 + 0.242, "tri", 100, -40),  # cluster 2 with C
        _fp("c5m-E", LAT0 + 0.350, LON0 + 0.020, "ell", 100, 15),  # far north (~39 km)
    ]

    # C5-holes: irregular fields of varied size, 3 with holes (1 / 2 / 3),
    # moderate spread. The "some with holes, some without" requirement.
    # (Hole fields use convex-ish templates so the center region stays inside.)
    layouts["C5holes"] = [
        _fp("c5h-A", LAT0, LON0, "quad", 203, 10, holes=[hole(LAT0, LON0, 0.0018, 0.0026)]),
        _fp("c5h-B", LAT0 + 0.004, LON0 + 0.030, "tri", 100, -30),  # no holes
        _fp(
            "c5h-C",
            LAT0,
            LON0 + 0.075,
            "trap",
            203,
            5,
            holes=[
                hole(LAT0, LON0 + 0.075 - 0.004, 0.0030, 0.0012),
                hole(LAT0, LON0 + 0.075 + 0.004, 0.0030, 0.0012),
            ],
        ),
        _fp("c5h-D", LAT0 + 0.090, LON0 + 0.030, "pent", 100, 45),  # no holes
        _fp(
            "c5h-E",
            LAT0 + 0.050,
            LON0 + 0.110,
            "quad",
            203,
            -18,
            holes=[
                hole(LAT0 + 0.050 - 0.0025, LON0 + 0.110 - 0.0035, 0.0010, 0.0014),
                hole(LAT0 + 0.050 + 0.0025, LON0 + 0.110 + 0.0035, 0.0010, 0.0014),
                hole(LAT0 + 0.050 + 0.0025, LON0 + 0.110 - 0.0035, 0.0010, 0.0014),
            ],
        ),
    ]

    # C10-grid: 2x5 grid positions, ~3 km spacing, irregular parcels. Scaling test.
    grid = []
    shapes10 = ["quad", "trap", "pent", "tri"]
    for r in range(2):
        for c in range(5):
            idx = r * 5 + c
            grid.append(
                _fp(
                    f"c10-{idx:02d}",
                    LAT0 + r * 0.025,
                    LON0 + c * 0.040,
                    shapes10[idx % 4],
                    100,
                    (idx * 25) % 360 - 40,
                )
            )
    layouts["C10grid"] = grid

    # C5-size: strong field-size heterogeneity (256 down to 16 ha) at moderate
    # spread. The clean campaign for per-field fleet selection: large fields
    # reward endurance/parallelism, small fields reward the cheapest airframe.
    layouts["C5size"] = [
        _fp("c5s-A", LAT0, LON0, "quad", 256, 20),
        _fp("c5s-B", LAT0 + 0.004, LON0 + 0.055, "trap", 144, -10),
        _fp("c5s-C", LAT0 + 0.045, LON0 + 0.010, "pent", 100, 55),
        _fp("c5s-D", LAT0 + 0.050, LON0 + 0.060, "tri", 25, -25),
        _fp("c5s-E", LAT0 + 0.025, LON0 + 0.100, "quad", 16, 80),
    ]

    # C15-scatter: 15 irregular fields scattered over ~20 x 21 km with local
    # clusters and mixed sizes -- the "one working day" stress test: a real
    # combinatorial tour space (15!), day-limit pressure, and fleet-selection
    # pressure at the same time. Offsets are hard-coded (deterministic).
    # Field areas 16-100 ha: one battery charge covers a whole field, so each
    # field is a single sortie and the day is tight but feasible (~10-11 h of
    # flight+setup+transit vs the 8 h soft / 14 h hard limits). With 100 ha
    # defaults the minimum possible duration exceeds the 14 h hard limit --
    # structurally infeasible regardless of the optimizer.
    scatter = [
        (0.000, 0.000, None),
        (0.008, 0.030, None),
        (-0.004, 0.062, "small"),
        (0.030, 0.018, None),
        (0.036, 0.055, None),
        (0.060, 0.005, None),
        (0.055, 0.090, None),
        (0.020, 0.120, "small"),
        (0.075, 0.140, None),
        (0.100, 0.060, "big"),
        (0.110, 0.110, None),
        (0.130, 0.020, None),
        (0.150, 0.150, None),
        (0.090, 0.200, None),
        (0.160, 0.090, None),
    ]
    shapes15 = ["quad", "trap", "pent", "tri", "ell"]
    c15 = []
    for i, (dlat, dlon, size) in enumerate(scatter):
        area = 16 if size == "small" else 100 if size == "big" else 36
        c15.append(_fp(f"c15-{i:02d}", LAT0 + dlat, LON0 + dlon, shapes15[i % 5], area, (i * 37) % 360))
    layouts["C15scatter"] = c15

    return layouts


def make_field(owner, spec):
    holes_serialized = json.dumps(spec["holes"]) if spec["holes"] else "[]"
    return Field.objects.create(
        owner=owner,
        name=f"EXP:{spec['name']}",
        points_serialized=json.dumps(spec["corners"]),
        road_serialized=json.dumps(road_south_of(spec["corners"])),
        holes_serialized=holes_serialized,
    )


def centroid(corners):
    lat = sum(c[0] for c in corners) / len(corners)
    lon = sum(c[1] for c in corners) / len(corners)
    return lat, lon


def main():
    user, _ = User.objects.get_or_create(username=EXP_USER)

    # Idempotent reset: drop previously generated experiment campaigns + fields.
    Campaign.objects.filter(owner=user).delete()
    Field.objects.filter(owner=user, name__startswith="EXP:").delete()

    drones = get_fleet()
    print(f"fleet: {[(d.id, d.name) for d in drones]}")

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
            centers.append(centroid(spec["corners"]))
        manifest[role] = campaign.id

        # Verification: pairwise transit distances along default order,
        # field areas (shoelace in km, -> ha), hole containment.
        seg = []
        for i in range(1, len(centers)):
            dlat = centers[i][0] - centers[i - 1][0]
            dlon = centers[i][1] - centers[i - 1][1]
            seg.append(round(km(dlat, dlon), 1))
        areas = []
        for spec in specs:
            xy = [((c[1] - LON0) * KM_PER_DEG_LON, (c[0] - LAT0) * KM_PER_DEG_LAT) for c in spec["corners"]]
            areas.append(round(_shoelace(xy) * 100))  # km^2 -> ha
            if spec["holes"]:
                from shapely.geometry import Polygon

                fpoly = Polygon([(c[1], c[0]) for c in spec["corners"]])
                for h in spec["holes"]:
                    hpoly = Polygon([(c[1], c[0]) for c in h])
                    if not fpoly.contains(hpoly):
                        print(f"  !! hole NOT inside {spec['name']}")
        n_holes = sum(len(s["holes"]) for s in specs)
        print(
            f"[{campaign.id}] EXP:{role:10s} fields={len(specs)} holes={n_holes} "
            f"areas(ha)={areas} consec-gaps(km)={seg}"
        )

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest -> {MANIFEST_PATH}")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
