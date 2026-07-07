"""Add the C3big campaign: very large fields where within-field parallelism
is a first-class economic decision.

Field A (2.8 x 2.8 km, ~780 ha) needs ~40+ km of sweep -- covering it with one
airframe (even the 60 km-range M300) takes ~6 h of flying, and covering the
whole campaign single-threaded takes ~12 h, deep into the overtime penalty
(8 h soft limit). Splitting the big fields across several distinct airframes
(concurrent sorties) compresses the day to ~8-9 h at the price of extra crew
(the salary term multiplies by the number of distinct airframes used). This is
the campaign where the drones gene -- composition AND order of the launch
sequence, since sweep chunks are assigned greedily up to each airframe's
battery limit -- is the dominant lever, unlike everywhere else.

Additive + idempotent: only touches the EXP:C3big campaign and its fields.
Updates scripts/exp_manifest.json in place.

Run: venv39\\Scripts\\python.exe scripts/exp_campaign_big.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
import django

django.setup()

from django.contrib.auth.models import User  # noqa: E402

from mainapp.models import Campaign, CampaignField, Field  # noqa: E402
from scripts.exp_campaigns import (  # noqa: E402
    EXP_USER,
    GRID_STEP,
    HOURLY_PRICE,
    LAT0,
    LON0,
    MANIFEST_PATH,
    START_PRICE,
    TRUCK_SPEED,
    _fp,
    get_fleet,
    make_field,
)


def main():
    user, _ = User.objects.get_or_create(username=EXP_USER)
    Campaign.objects.filter(owner=user, name="EXP:C3big").delete()
    Field.objects.filter(owner=user, name__startswith="EXP:c3b-").delete()

    drones = get_fleet()

    # Irregular parcels area-matched to the original squares: ~780/400/100 ha.
    specs = [
        _fp("c3b-A", LAT0, LON0, "pent", 780, 15),
        _fp("c3b-B", LAT0 + 0.010, LON0 + 0.070, "trap", 400, -25),
        _fp("c3b-C", LAT0 + 0.045, LON0 + 0.035, "quad", 100, 40),
    ]

    campaign = Campaign.objects.create(
        owner=user,
        name="EXP:C3big",
        grid_step=GRID_STEP,
        start_price=START_PRICE,
        hourly_price=HOURLY_PRICE,
        truck_speed_kmh=TRUCK_SPEED,
    )
    campaign.drones.add(*drones)
    for order, spec in enumerate(specs):
        field = make_field(user, spec)
        CampaignField.objects.create(campaign=campaign, field=field, default_order=order)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["C3big"] = campaign.id
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[{campaign.id}] EXP:C3big — irregular fields ~780/400/100 ha, manifest updated")


if __name__ == "__main__":
    main()
