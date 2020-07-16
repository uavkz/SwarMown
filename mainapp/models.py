from django.db import models


class Field(models.Model):
    class Meta:
        verbose_name = "Поле"
        verbose_name_plural = "Поля"

    name = models.CharField(max_length=250, unique=True)
    points_serialized = models.TextField() # Json Serialized [[lat, lon], [lat, lon], ...]
    road_serialized = models.TextField(default=[]) # Json Serialized [[lat, lon], [lat, lon], ...]
