import json

from django.core import serializers
from rest_framework import viewsets
from rest_framework.response import Response

from mainapp.models import *


# Create your views here.
class FieldViewSet(viewsets.ViewSet):
    def create(self, request):
        if "name" not in request.POST or not request.POST['name']:
            return Response({"status": 500, "error": "Пожалуйста введите имя"})
        if "points_serialized" not in request.POST or not request.POST['points_serialized']:
            return Response({"status": 500, "error": "Пожалуйста выберите точки"})
        if "road_serialized" not in request.POST or not request.POST['road_serialized']:
            return Response({"status": 500, "error": "Пожалуйста выберите дорогу"})
        if Field.objects.filter(name=self.request.POST['name']).exists():
            return Response({"status": 500, "error": "Поле с таким именем уже существует"})
        try:
            Field.objects.create(
                name=self.request.POST['name'],
                points_serialized=self.request.POST['points_serialized'],
                road_serialized=self.request.POST['road_serialized'],
                holes_serialized=json.dumps([hole for hole in json.loads(self.request.POST.get('holes_serialized', '[]')) if len(hole) >= 3])
            )
        except Exception as e:
            return Response({"status": 500, "error": str(e)})
        return Response({"status": 200}, status=200)


class WaypointsViewSet(viewsets.ViewSet):
    def list(self, request):
        mission = Mission.objects.get(id=request.GET.get('mission_id'))
        if mission.current_waypoints_status != 2 or True:
            return Response({"error": "Маршрут не готов"}, status=500)
        next_waypoint = mission.current_waypoints.filter(status=0).order_by('index').first()
        next_waypoint = json.loads(serializers.serialize('json', [next_waypoint])[1:-1])
        waypoint_pk = next_waypoint['pk']
        next_waypoint = next_waypoint['fields']
        next_waypoint['id'] = waypoint_pk
        return Response({
            "next_waypoint": next_waypoint
        }, status=200)
