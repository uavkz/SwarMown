from django.contrib import admin
from .models import *


class FieldAdmin(admin.ModelAdmin):
    list_display = ('name', )
    list_filter = ()
    search_fields = ('name', )


admin.site.register(Field, FieldAdmin)
