from django.contrib import admin
from .models import *


class FieldAdmin(admin.ModelAdmin):
    list_display = ('name', )
    list_filter = ()
    search_fields = ('name', )


class MissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'type', 'field', 'grid_step', 'datetime')
    list_filter = ('status', 'type', )
    search_fields = ('name', )


class DroneAdmin(admin.ModelAdmin):
    list_display = ('name', 'model', 'max_speed', 'max_height', 'max_distance_no_load', 'weight')
    list_filter = ()
    search_fields = ('name', 'model', )


class WaypointAdmin(admin.ModelAdmin):
    list_display = ('mission', 'drone', 'datetime', 'height', 'speed', 'acceleration', 'spray_on', )
    list_filter = ('mission', 'drone', 'spray_on', )
    search_fields = ('name', )


admin.site.register(Field, FieldAdmin)
admin.site.register(Mission, MissionAdmin)
admin.site.register(Drone, DroneAdmin)
admin.site.register(Waypoint, WaypointAdmin)
