import json

from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView, ListView

from mainapp.models import *
from mainapp.services_draw import *


class Index(View):
    def get(self, request, **kwargs):
        return HttpResponseRedirect(reverse_lazy('mainapp:list_mission'))


class SimulateMissionView(TemplateView):
    template_name = "mainapp/simulate_mission.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mission'] = Mission.objects.get(id=kwargs['mission_id'])

        field_obj = context['mission'].field
        field = json.loads(field_obj.points_serialized)
        field = [[y, x] for (x, y) in field]
        road = json.loads(field_obj.road_serialized)
        road = [[y, x] for (x, y) in road]

        grid_step = context['mission'].grid_step
        number_of_drones = context['mission'].drones.all().count()
        grid = get_grid(field, grid_step)
        initial_position = get_initial_position(field, grid, road)
        # [x, y, z, is_active]

        context['field_flat'] = [coord for point in field for coord in point]
        context['field'] = field
        context['field_id'] = field_obj.id if field_obj else ""
        context['road'] = road
        context['grid'] = grid
        context['grid_step'] = grid_step
        context['initial'] = initial_position
        context['number_of_drones'] = number_of_drones
        return context


class ManageRouteView(TemplateView):
    template_name = "mainapp/manage_route.html"

    def handle(self, context):
        car_move = self.request.GET.get("carMove", "no")
        direction = self.request.GET.get("direction", "simple")
        target = self.request.GET.get("target", "general")
        height_diff = self.request.GET.get("heightDiff", False) == "on"
        round_start_zone = self.request.GET.get("roundStartZone", False) == "on"
        feature3 = self.request.GET.get("feature3", False) == "on"
        feature4 = self.request.GET.get("feature4", False) == "on"

        field_obj = context['mission'].field
        field = json.loads(field_obj.points_serialized)
        field = [[y, x] for (x, y) in field]
        road = json.loads(field_obj.road_serialized)
        road = [[y, x] for (x, y) in road]

        grid_step = context['mission'].grid_step
        number_of_drones = context['mission'].drones.all().count()
        grid = get_grid(field, grid_step)
        initial_position = get_initial_position(field, grid, road)
        # [x, y, z, is_active]

        context['field_flat'] = [coord for point in field for coord in point]
        context['field'] = field
        context['field_id'] = field_obj.id if field_obj else ""
        context['road'] = road
        context['grid'] = grid
        context['grid_step'] = grid_step
        context['initial'] = initial_position
        context['number_of_drones'] = number_of_drones
        context['waypoints'] = self.get_route()

    def get_route(self):
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mission'] = Mission.objects.get(id=kwargs['mission_id'])
        self.handle(context)
        return context


class MissionsCreateView(TemplateView):
    template_name = "mainapp/add_mission.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['types'] = Mission.TYPES
        context['fields'] = Field.objects.all()
        context['drones'] = Drone.objects.all()
        return context

    def post(self, request, **kwargs):
        m = Mission.objects.create(
            name=request.POST['name'],
            description=request.POST['description'],
            type=request.POST['type'],
            field_id=request.POST['field'],
            grid_step=request.POST['grid_step'],
        )
        m.drones.add(*request.POST.getlist('drones'))
        return HttpResponseRedirect(reverse_lazy('mainapp:list_mission'))


class MissionsListView(ListView):
    template_name = "mainapp/list_mission.html"
    queryset = Mission.objects.all().order_by('-id')
