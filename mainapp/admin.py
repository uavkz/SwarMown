from django.contrib import admin
from .models import *


class FieldAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', )
    list_filter = ('owner', )
    search_fields = ('name', )


class MissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'status', 'current_waypoints_status', 'type', 'field', 'start_price', 'hourly_price', 'grid_step', 'datetime')
    list_filter = ('status', 'type', 'current_waypoints_status', 'owner', 'field', )
    search_fields = ('name', )


class DroneAdmin(admin.ModelAdmin):
    list_display = ('name', 'model', 'max_speed', 'max_distance_no_load', 'slowdown_ratio_per_degree',
                    'min_slowdown_ratio', 'price_per_cycle', 'price_per_kilometer', 'price_per_hour',)
    list_filter = ()
    search_fields = ('name', 'model', )


class WaypointAdmin(admin.ModelAdmin):
    list_display = ('drone', 'datetime', 'index', 'lat', 'lon', 'speed', 'spray_on', 'status', )
    list_filter = ('mission', 'drone', 'spray_on', 'status', )
    search_fields = ('name', )


admin.site.register(Field, FieldAdmin)
admin.site.register(Mission, MissionAdmin)
admin.site.register(Drone, DroneAdmin)
admin.site.register(Waypoint, WaypointAdmin)
