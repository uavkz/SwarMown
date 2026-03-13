"""Batch runner for genetic_holes.py across missions with holes."""

import datetime
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")

import django

django.setup()

from mainapp.models import Mission  # noqa: E402

N_CORES = 8

for mission in Mission.objects.filter(id__in=[29, 30, 31, 32]).exclude(field__holes_serialized="[]"):
    ngen = 25
    population_size = 50
    max_time = 8
    borderline_time = 2
    max_working_speed = 7
    mutation_chance = 0.1
    filename = f"test_subpolygons_{mission.name.replace(' ', '_')}_{mission.id}"

    print(filename)
    d1 = datetime.datetime.now()
    os.system(
        f"python -m scoop -n {N_CORES} scripts/genetic_holes.py"
        f" --mission_id {mission.id} --ngen {ngen}"
        f" --population_size {population_size} --filename {filename}"
        f" --max-time {max_time} --borderline_time {borderline_time}"
        f" --max_working_speed {max_working_speed} --mutation_chance {mutation_chance}"
    )
    elapsed = (datetime.datetime.now() - d1).total_seconds()
    print(f"Time: {elapsed}\n")
