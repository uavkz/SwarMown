import json

from django.views.generic import TemplateView

from mainapp.algorithms import WAYPOINTS_ALGORITHMS
from mainapp.models import *
from mainapp.services_draw import *


class MownView(TemplateView):
    template_name = "mainapp/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fields'] = Field.objects.all()

        if not self.request.GET.get('field'):
            field = get_field()
        else:
            field = Field.objects.get(id=self.request.GET.get('field')).points_serialized
            field = json.loads(field)
            field = [[y, x] for (x, y) in field]

        grid_step = float(self.request.GET.get("grid_step", 0.001))
        grid = get_grid(field, grid_step)
        initial_position = get_initial_position(field, grid)
        # [x, y, z, is_active]
        waypoints, pickup_waypoints = WAYPOINTS_ALGORITHMS[self.request.GET.get("algorithm", "zamboni")]['callable'](grid, initial_position)
        context['field_flat'] = [coord for point in field for coord in point]
        context['field'] = field
        context['grid'] = grid
        context['grid_step'] = grid_step
        context['initial'] = initial_position
        context['waypoints'] = waypoints
        context['pickup_waypoints'] = pickup_waypoints
        context['number_of_drones'] = len(waypoints)
        return context
