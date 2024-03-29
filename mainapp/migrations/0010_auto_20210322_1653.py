# Generated by Django 3.0.3 on 2021-03-22 10:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mainapp', '0009_auto_20210319_1358'),
    ]

    operations = [
        migrations.AddField(
            model_name='mission',
            name='hourly_price',
            field=models.FloatField(default=3, verbose_name='Цена за один час (оплата пилоту)'),
        ),
        migrations.AddField(
            model_name='mission',
            name='start_price',
            field=models.FloatField(default=3, verbose_name='Цена за один старт (оплата пилоту)'),
        ),
        migrations.AlterField(
            model_name='drone',
            name='max_distance_no_load',
            field=models.FloatField(verbose_name='Максимальная дальность полета (км)'),
        ),
    ]
