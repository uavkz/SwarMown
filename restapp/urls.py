from django.urls import include, path
from rest_framework import routers

from restapp.views import FieldViewSet, WaypointsViewSet

router = routers.DefaultRouter()
router.register("field", FieldViewSet, basename="field")
router.register("waypoints", WaypointsViewSet, basename="waypoints")

app_name = "restapp"

urlpatterns = [
    path("", include(router.urls)),
]
