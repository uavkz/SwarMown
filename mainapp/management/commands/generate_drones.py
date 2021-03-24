import random

from django.core.management.base import BaseCommand

from mainapp.models import Drone


class Command(BaseCommand):

    def handle(self, *args, **options):
        self.run()

    def run(self):
        Drone.objects.all().delete()

        for drone_num in range(int(random.gauss(50, 15))):
            performance_rate = max(random.gauss(100, 15), 0.01)
            price_rate = max(random.gauss(100, 15), 0.01)

            Drone.objects.create(
                name=f"Дрон №{drone_num} perf={round(performance_rate, 1)} price={round(price_rate, 1)}",
                model=f"Дрон №{drone_num}",
                max_speed=max(random.gauss(10, 5), 1) * (performance_rate / 100),
                max_distance_no_load=max(random.gauss(5, 4), 1) * (performance_rate / 100),
                slowdown_ratio_per_degree=max(random.gauss(0.75 / 180, 0.25 / 180), 0.1 / 180) / (performance_rate / 100),
                min_slowdown_ratio=max(random.gauss(0.05, 0.02), 0.001) * (performance_rate / 100),

                price_per_cycle=max(random.gauss(1000, 500) / 500, 0.5) * (price_rate / 100),
                price_per_kilometer=max(random.gauss(1000, 500) / random.gauss(100000, 25000), 0.001) * (price_rate / 100),
                price_per_hour=max(random.gauss(1000, 500) / random.gauss(10000, 2500), 0.01) * (price_rate / 100),

                max_height=1,
                weight=15,
                max_load=15,
            )
