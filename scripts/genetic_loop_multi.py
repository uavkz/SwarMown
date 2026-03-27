"""Batch runner for multi-field GA experiments.

Runs all combinations of crossover x mutation operators,
plus ablation variants, for each campaign.
"""

import datetime
import itertools
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
import django

django.setup()

from mainapp.models import Campaign  # noqa: E402

N_CORES = 8
NGEN = 25
POPULATION_SIZE = 50
MAX_TIME = 12
BORDERLINE_TIME = 4
MAX_WORKING_SPEED = 7
MUTATION_CHANCE = 0.1

CROSSOVER_TYPES = ["ox", "pmx", "cx"]
MUTATION_TYPES = ["swap", "insert", "inversion"]
ABLATIONS = ["full", "single_direction", "single_start", "fixed_order", "single_drones"]

# --- Configure campaign IDs here ---
CAMPAIGN_IDS = []  # e.g. [1, 2, 3]

campaigns = Campaign.objects.filter(id__in=CAMPAIGN_IDS) if CAMPAIGN_IDS else Campaign.objects.all()

for campaign in campaigns:
    # Phase 1: operator comparison (3x3 = 9 runs, all with ablation=full)
    for cx_type, mut_type in itertools.product(CROSSOVER_TYPES, MUTATION_TYPES):
        filename = f"multi_{campaign.name.replace(' ', '_')}_{campaign.id}_{cx_type}_{mut_type}"
        print(f"{filename} -- {datetime.datetime.now()}")
        d1 = datetime.datetime.now()
        os.system(
            f"python -m scoop -n {N_CORES} scripts/genetic_multi.py"
            f" --campaign_id {campaign.id} --ngen {NGEN}"
            f" --population_size {POPULATION_SIZE} --filename {filename}"
            f" --max-time {MAX_TIME} --borderline_time {BORDERLINE_TIME}"
            f" --max_working_speed {MAX_WORKING_SPEED}"
            f" --mutation_chance {MUTATION_CHANCE}"
            f" --order_crossover {cx_type} --order_mutation {mut_type}"
        )
        elapsed = (datetime.datetime.now() - d1).total_seconds()
        print(f"  Time: {elapsed:.1f}s\n")

    # Phase 2: ablation comparison (use ox+swap as baseline operators)
    for ablation in ABLATIONS:
        if ablation == "full":
            continue  # already run in Phase 1 as ox_swap
        filename = f"multi_{campaign.name.replace(' ', '_')}_{campaign.id}_ablation_{ablation}"
        print(f"{filename} -- {datetime.datetime.now()}")
        d1 = datetime.datetime.now()
        os.system(
            f"python -m scoop -n {N_CORES} scripts/genetic_multi.py"
            f" --campaign_id {campaign.id} --ngen {NGEN}"
            f" --population_size {POPULATION_SIZE} --filename {filename}"
            f" --max-time {MAX_TIME} --borderline_time {BORDERLINE_TIME}"
            f" --max_working_speed {MAX_WORKING_SPEED}"
            f" --mutation_chance {MUTATION_CHANCE}"
            f" --order_crossover ox --order_mutation swap"
            f" --ablation {ablation}"
        )
        elapsed = (datetime.datetime.now() - d1).total_seconds()
        print(f"  Time: {elapsed:.1f}s\n")
