try:
    import os
    import sys

    from django.conf import settings

    sys.path.append('C:\\Users\\KindYAK\\Desktop\\SwarMown\\')
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
    import django
    django.setup()
except Exception as e:
    pass

import os

from mainapp.models import Mission


for mission in Mission.objects.all().filter(id__in=[12]):
    mission_id = mission.id
    ngen = 2
    population_size = 4
    max_time = 10
    borderline_time = 5
    max_working_speed = 5
    mutation_chance = 0.05
    filename = f"test_{mission_id}"

    print(filename)
    os.system(f"python -m scoop scripts\\genetic.py --mission_id {mission_id} --ngen {ngen} --population_size {population_size} --filename {filename} --max-time {max_time} --borderline_time {borderline_time} --max_working_speed {max_working_speed} --mutation_chance {mutation_chance}")
