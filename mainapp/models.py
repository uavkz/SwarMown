from django.contrib.auth.models import User
from django.db import models

from mainapp.utils import waypoints_distance, waypoints_flight_time
from swarmown import settings


class Field(models.Model):
    class Meta:
        verbose_name = "Поле"
        verbose_name_plural = "Поля"
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"], name="unique_field_name_per_owner"
            )
        ]

    name = models.CharField(max_length=251)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="fields",
        null=True,
        blank=True,
        verbose_name="Владелец",
    )

    points_serialized = models.TextField() # Json Serialized [[lat, lon], [lat, lon], ...]
    road_serialized = models.TextField(default=[]) # Json Serialized [[lat, lon], [lat, lon], ...]
    holes_serialized = models.TextField(default=[], verbose_name="Препятствия (Serialized)") # Json Serialized [# First hole # [[lat, lon], [lat, lon], ...], # Second hole # [[lat, lon], [lat, lon], ...], ...]

    def __str__(self):
        return f"{self.name}"

#
# import json
# from shapely.geometry import shape
#
# f = Field.objects.get(id=26)
# j = json.loads(f.points_serialized)
#
# co = {"type": "Polygon", "coordinates": [
#     [
#         (j[1], j[0]) for j in j
#     ]
# ]}
# lon, lat = zip(*co['coordinates'][0])
# from pyproj import Proj
# # 43.27038611295692, 76.7296543207424
# # 43.14601796133043, 77.03074836368798
# pa = Proj("+proj=aea +lat_1=1 +lat_2=0 +lat_0=89 +lon_0=179")
#
# x, y = pa(lon, lat)
# cop = {"type": "Polygon", "coordinates": [zip(x, y)]}
# print(round(shape(cop).area))  # 268952044107.43506

class Mission(models.Model):
    class Meta:
        verbose_name = "Миссия"
        verbose_name_plural = "Миссии"
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"], name="unique_mission_name_per_owner"
            )
        ]

    STATUSES = (
        (-2, "Критическая ошибка"),
        (-1, "Отмена"),
        (0, "Не запущен"),
        (1, "В ожидании"),
        (2, "В работе"),
        (3, "Завершен"),
    )

    WAYPOINTS_STATUSES = (
        (0, "Не рассчитано"),
        (1, "В процессе расчета"),
        (2, "Готово"),
    )

    TYPES = (
        (1, "Опрыскивание"),
        (2, "Аеро-фото-съемка"),
        (3, "Детальная съемка"),
    )

    name = models.CharField(max_length=250, verbose_name="Название")
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="missions",
        null=True,
        blank=True,
        verbose_name="Владелец",
    )

    description = models.TextField(null=True, blank=True, verbose_name="Описание")
    datetime = models.DateTimeField(auto_now_add=True, verbose_name="Время создания")

    status = models.SmallIntegerField(default=0, choices=STATUSES, verbose_name="Статус")
    type = models.SmallIntegerField(choices=TYPES, verbose_name="Тип задачи")

    field = models.ForeignKey('Field', on_delete=models.CASCADE, verbose_name="Поля")
    grid_step = models.FloatField(default=100, verbose_name="Шаг решетки (м)")
    drones = models.ManyToManyField('Drone', blank=True, verbose_name="Дроны")
    current_waypoints_status = models.SmallIntegerField(default=0, choices=WAYPOINTS_STATUSES, verbose_name="Статус маршрута")
    current_waypoints = models.ManyToManyField('Waypoint', blank=True, verbose_name="Текущий путь", related_name="mission")
    waypoints_history = models.ManyToManyField('Waypoint', blank=True, verbose_name="История", related_name="mission_history")

    start_price = models.FloatField(default=3, verbose_name="Цена за один старт (оплата пилоту, $)")
    hourly_price = models.FloatField(default=10, verbose_name="Цена за один час (оплата пилоту, $)")

    def __str__(self):
        return f"{self.name} ({self.type_verbose}) {self.status}"

    @property
    def status_verbose(self):
        return dict(self.STATUSES)[self.status]

    @property
    def current_waypoints_status_verbose(self):
        return dict(self.WAYPOINTS_STATUSES)[self.current_waypoints_status]

    @property
    def type_verbose(self):
        return dict(self.TYPES)[self.type]

    @property
    def drones_verbose(self):
        return ", ".join([str(d) for d in self.drones.all().order_by('id')])

    @property
    def simulated_distance(self):
        return waypoints_distance(self.current_waypoints.all())

    @property
    def history_distance(self):
        return waypoints_distance(self.waypoints_history.all())

    @property
    def simulated_flight_time(self):
        return waypoints_flight_time(self.current_waypoints.all().order_by('index'))

    @property
    def history_flight_time(self):
        return waypoints_flight_time(self.waypoints_history.all().order_by('index'))


class Drone(models.Model):
    class Meta:
        verbose_name = "Дрон"
        verbose_name_plural = "Дроны"
        unique_together = ("name", "model")

    name = models.CharField(max_length=250, verbose_name="Название")
    model = models.CharField(max_length=250, verbose_name="Модель дрона")

    max_speed = models.FloatField(default=15, verbose_name="Максимальная скорость (км/ч)")
    max_distance_no_load = models.FloatField(verbose_name="Максимальная дальность полета (км)")

    slowdown_ratio_per_degree = models.FloatField(default=0.9/180, verbose_name="Коэффициент замедление на один градус поворота")
    min_slowdown_ratio = models.FloatField(default=0.01, verbose_name="Минимальный коэффициент замедления при повороте")

    price_per_cycle = models.FloatField(default=3, verbose_name="Цена за один полет ($)")
    price_per_kilometer = models.FloatField(default=0.1, verbose_name="Цена за километр ($)")
    price_per_hour = models.FloatField(default=0.01, verbose_name="Цена за час ($)")

    max_height = models.FloatField(default=1, verbose_name="Максимальная высота (км)")
    weight = models.FloatField(verbose_name="Вес дрона (кг)")
    max_load = models.FloatField(verbose_name="Максимальная нагрузка (кг)")

    def __str__(self):
        return f"{self.name} ({self.model})"


class Waypoint(models.Model):
    class Meta:
        verbose_name = "Waypoint облета"
        verbose_name_plural = "Waypointы облетов"

    STATUSES = (
        (-1, "История"),
        (0, "Не начат"),
        (1, "В процессе"),
        (2, "Завершен"),
    )

    drone = models.ForeignKey('Drone', on_delete=models.CASCADE)

    status = models.SmallIntegerField(default=0, choices=STATUSES, verbose_name="Статус")

    datetime = models.DateTimeField(null=True, blank=True, verbose_name="Дата и время Waypointа")
    index = models.PositiveIntegerField(null=True, blank=True, verbose_name="Порядковый номер")
    lat = models.FloatField(verbose_name="Широта")
    lon = models.FloatField(verbose_name="Долгота")
    height = models.FloatField(verbose_name="Высота")

    speed = models.FloatField(verbose_name="Скорость полета")
    acceleration = models.FloatField(verbose_name="Ускорение")
    spray_on = models.BooleanField(null=True, blank=True, verbose_name="Включено ли разбрызгивание")

    def __str__(self):
        return f"{self.mission} ({self.drone}) - {self.datetime}"

    @property
    def status_verbose(self):
        return dict(self.STATUSES)[self.status]
