try:
    import os
    import sys

    from django.conf import settings

    sys.path.append('C:\\Users\\HaveToCook\\Desktop\\SwarMown\\')
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
    import django
    django.setup()
except Exception as e:
    pass

import os

from mainapp.models import Mission


for mission in Mission.objects.all():
    mission_id = mission.id
    ngen = 150
    population_size = 250
    max_time = 8
    borderline_time = 2
    max_working_speed = 7
    mutation_chance = 0.1
    filename = f"test_{mission.name.replace(' ', '_')}_{mission.id}"

    print(filename)
    os.system(f"python -m scoop scripts\\genetic.py --mission_id {mission_id} --ngen {ngen} --population_size {population_size} --filename {filename} --max-time {max_time} --borderline_time {borderline_time} --max_working_speed {max_working_speed} --mutation_chance {mutation_chance}")
