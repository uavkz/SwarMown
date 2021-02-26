# Generated by Django 3.0.3 on 2021-02-19 11:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mainapp', '0005_mission_current_waypoints_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='drone',
            name='max_load',
            field=models.FloatField(default=0, verbose_name='Максимальная нагрузка'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='mission',
            name='current_waypoints',
            field=models.ManyToManyField(blank=True, related_name='mission', to='mainapp.Waypoint', verbose_name='Текущий путь'),
        ),
        migrations.AlterField(
            model_name='mission',
            name='waypoints_history',
            field=models.ManyToManyField(blank=True, related_name='mission_history', to='mainapp.Waypoint', verbose_name='История'),
        ),
    ]