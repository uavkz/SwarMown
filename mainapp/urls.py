from django.urls import path

from .views import *

app_name = 'mainapp'

urlpatterns = [
    path('', MownView.as_view(), name="index"),
    path('add-field/', TemplateView.as_view(template_name="mainapp/add_field.html"), name="add_field"),

    path('add-mission/', MissionsCreateView.as_view(), name="add_mission"),
    path('list-mission/', MissionsListView.as_view(), name="list_mission"),
]
