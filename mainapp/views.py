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


class MownView(TemplateView):
    template_name = "mainapp/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fields'] = Field.objects.all()

        field_obj = None
        if not self.request.GET.get('field'):
            field = get_field()
            road = []
        else:
            field_obj = Field.objects.get(id=self.request.GET.get('field'))
            field = json.loads(field_obj.points_serialized)
            field = [[y, x] for (x, y) in field]
            road = json.loads(field_obj.road_serialized)
            road = [[y, x] for (x, y) in road]

        grid_step = float(self.request.GET.get("grid_step", 0.001))
        number_of_drones = int(self.request.GET.get("number_of_drones", 2))
        grid = get_grid(field, grid_step)
        initial_position = get_initial_position(field, grid, road)
        # [x, y, z, is_active]
        # waypoints, pickup_waypoints = generate_zamboni(grid, initial_position, road, number_of_drones)
        context['field_flat'] = [coord for point in field for coord in point]
        context['field'] = field
        context['field_id'] = field_obj.id if field_obj else ""
        context['road'] = road
        context['grid'] = grid
        context['grid_step'] = grid_step
        context['initial'] = initial_position
        context['number_of_drones'] = number_of_drones
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
