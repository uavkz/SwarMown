from django.conf.urls import include, url
from rest_framework import routers

from restapp.views import *

router = routers.DefaultRouter()
router.register("field", FieldViewSet, basename="field")
router.register("waypoints", WaypointsViewSet, basename="waypoints")

app_name = 'restapp'

urlpatterns = [
    url('', include(router.urls)),
]
