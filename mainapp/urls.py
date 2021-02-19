from django.urls import path

from .views import *

app_name = 'mainapp'

urlpatterns = [
    path('', Index.as_view(), name="index"),

    path('add-field/', TemplateView.as_view(template_name="mainapp/add_field.html"), name="add_field"),

    path('add-mission/', MissionsCreateView.as_view(), name="add_mission"),
    path('list-mission/', MissionsListView.as_view(), name="list_mission"),

    path('manage-route/<int:mission_id>/', ManageRouteView.as_view(), name="manage_route"),

    path('simulating-mission/<int:mission_id>/', SimulateMissionView.as_view(), name="simulate_mission"),
]
