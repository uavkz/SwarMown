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
        if Field.objects.filter(name=self.request.POST['name']).exists():
            return Response({"status": 500, "error": "Поле с таким именем уже существует"})
        try:
            Field.objects.create(name=self.request.POST['name'], points_serialized=self.request.POST['points_serialized'])
        except Exception as e:
            return Response({"status": 500, "error": str(e)})
        return Response({"status": 200}, status=200)
