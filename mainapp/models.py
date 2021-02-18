from django.db import models


class Field(models.Model):
    class Meta:
        verbose_name = "Поле"
        verbose_name_plural = "Поля"

    name = models.CharField(max_length=250, unique=True)
    points_serialized = models.TextField() # Json Serialized [[lat, lon], [lat, lon], ...]
    road_serialized = models.TextField(default=[]) # Json Serialized [[lat, lon], [lat, lon], ...]

    def __str__(self):
        return f"{self.name}"


class Mission(models.Model):
    class Meta:
        verbose_name = "Миссия"
        verbose_name_plural = "Миссии"

    STATUSES = (
        (-2, "Критическая ошибка"),
        (-1, "Отмена"),
        (0, "Не запущен"),
        (1, "В ожидании"),
        (2, "В работе"),
        (3, "Завершен"),
    )

    TYPES = (
        (1, "Опрыскивание"),
        (2, "Аеро-фото-съемка"),
        (3, "Детальная съемка"),
    )

    name = models.CharField(max_length=250, verbose_name="Название", unique=True)
    description = models.TextField(null=True, blank=True, verbose_name="Описание")
    datetime = models.DateTimeField(auto_now_add=True, verbose_name="Время создания")

    status = models.SmallIntegerField(default=0, choices=STATUSES, verbose_name="Статус")
    type = models.SmallIntegerField(choices=TYPES, verbose_name="Тип задачи")

    field = models.ForeignKey('Field', on_delete=models.CASCADE, verbose_name="Поля")
    grid_step = models.FloatField(default=0.001, verbose_name="Шаг решетки")
    drones = models.ManyToManyField('Drone', verbose_name="Дроны")
    waypoints_history = models.ManyToManyField('Waypoint', verbose_name="История", related_name="mission_obj")

    def __str__(self):
        return f"{self.name} ({self.type}) {self.status}"

    @property
    def status_verbose(self):
        return dict(self.STATUSES)[self.status]

    @property
    def type_verbose(self):
        return dict(self.TYPES)[self.type]

    @property
    def drones_verbose(self):
        return ", ".join([str(d) for d in self.drones.all()])


class Drone(models.Model):
    class Meta:
        verbose_name = "Дрон"
        verbose_name_plural = "Дроны"
        unique_together = ("name", "model")

    name = models.CharField(max_length=250, verbose_name="Название")
    model = models.CharField(max_length=250, verbose_name="Модель дрона")

    max_speed = models.FloatField(verbose_name="Максимальная скорость")
    max_height = models.FloatField(verbose_name="Максимальная высота")
    max_distance_no_load = models.FloatField(verbose_name="Максимальная дальность полета без доп. нагрузки")

    weight = models.FloatField(verbose_name="Вес дрона")

    def __str__(self):
        return f"{self.name} ({self.model})"


class Waypoint(models.Model):
    class Meta:
        verbose_name = "Waypoint облета"
        verbose_name_plural = "Waypointы облетов"

    mission = models.ForeignKey('Mission', on_delete=models.CASCADE)
    drone = models.ForeignKey('Drone', on_delete=models.CASCADE)

    datetime = models.DateTimeField(verbose_name="Дата и время Waypointа")
    lat = models.FloatField(verbose_name="Широта")
    lon = models.FloatField(verbose_name="Долгота")
    height = models.FloatField(verbose_name="Высота")

    speed = models.FloatField(verbose_name="Скорость полета")
    acceleration = models.FloatField(verbose_name="Ускорение")
    spray_on = models.BooleanField(null=True, blank=True, verbose_name="Включено ли разбрызгивание")

    def __str__(self):
        return f"{self.mission} ({self.drone}) - {self.datetime}"
