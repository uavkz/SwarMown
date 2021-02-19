# Generated by Django 3.0.3 on 2021-02-19 06:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mainapp', '0004_auto_20210219_1210'),
    ]

    operations = [
        migrations.AddField(
            model_name='mission',
            name='current_waypoints_status',
            field=models.SmallIntegerField(choices=[(0, 'Не рассчитано'), (1, 'В процессе расчета'), (2, 'Готово')], default=0, verbose_name='Статус маршрута'),
        ),
    ]
