try:
    import os
    import sys

    from django.conf import settings

    sys.path.append('C:\\Архив\\Наука-старое\\UAV-Related\\SwarMown\\')
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
    import django
    django.setup()
except Exception as e:
    pass

import os

from mainapp.models import Mission

N_CORES = 8
for mission in Mission.objects.filter(id__in=[29, 30, 31, 32]).exclude(field__holes_serialized="[]"):
    mission_id = mission.id
    ngen = 25
    population_size = 50
    max_time = 8
    borderline_time = 2
    max_working_speed = 7
    mutation_chance = 0.1
    filename = f"test_subpolygons_{mission.name.replace(' ', '_')}_{mission.id}"

    print(filename)
    os.system(f"python -m scoop -n {N_CORES} scripts\\genetic_holes.py --mission_id {mission_id} --ngen {ngen} --population_size {population_size} --filename {filename} --max-time {max_time} --borderline_time {borderline_time} --max_working_speed {max_working_speed} --mutation_chance {mutation_chance}")
