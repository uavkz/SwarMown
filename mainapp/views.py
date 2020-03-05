from django.views.generic import TemplateView

from mainapp.services_draw import *


class MownView(TemplateView):
    template_name = "mainapp/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        field = get_field()
        grid = get_grid(field, 100)
        initial_drones = get_drones_initial_positions(field, grid)
        waypoints = get_waypoints(field, grid, initial_drones)
        context['field'] = [coord for point in field for coord in point]
        context['grid'] = grid
        context['initial_drones'] = initial_drones
        context['waypoints'] = waypoints
        return context
